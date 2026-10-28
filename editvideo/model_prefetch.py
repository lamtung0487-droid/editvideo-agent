"""Advisory Windows prefetch for the one mmap checkpoint about to be used.

No model copies or tensor changes. Windows can ignore this hint under pressure.
https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-prefetchvirtualmemory
"""
import os
import time
import json
import struct

def tensor_ranges(path,prefixes):
    """Merge byte ranges for selected safetensors tensors, including the header."""
    with open(path,'rb') as file:
        length=struct.unpack('<Q',file.read(8))[0]
        if not 0<length<16*1024*1024:raise ValueError('Invalid safetensors header size')
        header=json.loads(file.read(length));size=os.fstat(file.fileno()).st_size
    start=length+8;regions=[(0,start)]
    for name,value in header.items():
        if not any(name.startswith(p) for p in prefixes):continue
        a,b=value['data_offsets']
        if not 0<=a<=b<=size-start:raise ValueError('Invalid safetensors tensor range')
        regions.append((a+start,b+start))
    if len(regions)==1:raise ValueError('No requested tensors in checkpoint')
    merged=[]
    for a,b in sorted(regions):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return merged

def warm(path,check=lambda:None,regions=None):
    if os.name!='nt' or os.environ.get('EDITVIDEO_MODEL_PREFETCH','0')!='1':
        return {'applied':False,'reason':'not enabled on this platform'}
    import ctypes
    import msvcrt
    from ctypes import wintypes
    class Range(ctypes.Structure):
        _fields_=[('address',ctypes.c_void_p),('length',ctypes.c_size_t)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    prefetch=getattr(kernel,'PrefetchVirtualMemory',None)
    if prefetch is None:return {'applied':False,'reason':'Windows API unavailable'}
    prefetch.argtypes=[wintypes.HANDLE,ctypes.c_size_t,ctypes.POINTER(Range),wintypes.ULONG]
    prefetch.restype=wintypes.BOOL
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.CreateFileMappingW.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,wintypes.LPCWSTR]
    kernel.CreateFileMappingW.restype=wintypes.HANDLE
    kernel.MapViewOfFile.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,ctypes.c_size_t]
    kernel.MapViewOfFile.restype=ctypes.c_void_p
    kernel.UnmapViewOfFile.argtypes=[ctypes.c_void_p]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    started=time.monotonic();hinted=0
    try:
        with open(path,'rb') as file:
            size=os.fstat(file.fileno()).st_size
            # Read-only native mapping avoids a copy-on-write commit reservation.
            handle=kernel.CreateFileMappingW(msvcrt.get_osfhandle(file.fileno()),None,0x02,0,0,None)
            if not handle:raise ctypes.WinError(ctypes.get_last_error())
            address=None
            try:
                address=kernel.MapViewOfFile(handle,0x04,0,0,0)
                if not address:raise ctypes.WinError(ctypes.get_last_error())
                for a,b in regions or [(0,size)]:
                    if not 0<=a<b<=size:raise ValueError('Invalid prefetch range')
                    for offset in range(a,b,64*1024*1024):
                        check();length=min(64*1024*1024,b-offset)
                        entry=Range(address+offset,length)
                        if not prefetch(kernel.GetCurrentProcess(),1,ctypes.byref(entry),0):
                            return {'applied':False,'hinted_bytes':hinted,'windows_error':ctypes.get_last_error()}
                        hinted+=length
            finally:
                if address:kernel.UnmapViewOfFile(address)
                kernel.CloseHandle(handle)
    except OSError as error:
        return {'applied':False,'hinted_bytes':hinted,'windows_error':getattr(error,'winerror',None)}
    return {'applied':True,'hinted_bytes':hinted,'seconds':round(time.monotonic()-started,2),
            'note':'advisory cache hint; not a guarantee of residency or speedup'}
