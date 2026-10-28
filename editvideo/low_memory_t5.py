"""Keep T5 linear weights in FP8 storage; compute in the activation dtype.

The RTX 3060 needs no native FP8 GEMM. Accelerate brings each small module to
the GPU; its forward converts just that weight for BF16 computation. Norms
and the shared embedding stay BF16. No model architecture/quantization change.
"""
def patch(model):
    import types
    import torch
    import torch.nn.functional as F
    from transformers.models.t5.modeling_t5 import T5DenseGatedActDense,T5DenseActDense

    def linear(self,hidden):
        dtype=hidden.dtype
        return F.linear(hidden,self.weight.to(dtype),self.bias.to(dtype) if self.bias is not None else None)

    def gated(self,hidden):
        hidden=self.act(self.wi_0(hidden))*self.wi_1(hidden)
        return self.wo(self.dropout(hidden))

    def dense(self,hidden):
        return self.wo(self.dropout(self.act(self.wi(hidden))))

    for module in model.modules():
        if isinstance(module,torch.nn.Linear):module.forward=types.MethodType(linear,module)
        elif isinstance(module,T5DenseGatedActDense):module.forward=types.MethodType(gated,module)
        elif isinstance(module,T5DenseActDense):module.forward=types.MethodType(dense,module)
    return model
