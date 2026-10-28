# Legally usable 3D assets, period imagery/maps and elevation data for a Vietnamese historical documentary (1945-1975), headless Python + Blender 5.2

Research date: 2026-10-27. Scope: individual creator, internal and possibly published documentary. "Verified" means read on the provider's own page during this session. Some primary pages blocked automated fetches: UT Libraries (Anubis bot wall), si.edu terms (403), fab.com/eula (403), Edinburgh DataShare (403), and the USGS declassified pages (JS-rendered, empty to the fetcher). For those, the facts below come from search snippets of the same pages or from secondary sources, and each one is marked.

---

## 1. 3D models and materials: which sources are legally usable, what attribution, how to fetch

### Takeaway
Poly Haven (CC0, API free including commercial use), Blendkit/BlenderKit (Royalty Free or CC0, commercial OK, no attribution) and Smithsonian CC0 items are the safest sources. Sketchfab is the only large source of free Vietnam-era military vehicle models, but most of its free models are CC BY (credit required) and some are NC/ND. Its API returns only glTF/GLB/USDZ, needs a logged-in user, and the platform has had a turbulent 2024-2026 (store moved to Fab; KitBash acquisition reported August 2026). Fab/Megascans is mostly paid since 2025. Objaverse inherits per-object Sketchfab licences and adds nothing licence-wise.

### Cited Findings

**Poly Haven (HDRIs, textures, models)**
- All assets are CC0: "Our assets are all licensed as CC0, which is effectively Public Domain." Use for any purpose including commercial, no credit required, redistribution allowed "in a product you sell." — [Poly Haven License](https://polyhaven.com/license)
- Site content other than the assets (logos, example renders, user renders, text) is NOT CC0 and needs written permission. Site ToS prohibits "Web scraping or data mining without express permission". The public API at api.polyhaven.com is governed by separate API Terms. — [Poly Haven License](https://polyhaven.com/license)
- API terms: "The Poly Haven API is now free for everyone - including commercial use"; no API key or login for default endpoints. Condition: "make it clear to your users that the assets came from Poly Haven" when building a product/site/service on the live API. Attribution is "a condition of the API service, not of the assets". Every request needs a unique User-Agent header. No rate limits stated. Bulk downloading for research and AI/ML is listed as a supported use. — [Poly Haven API page](https://polyhaven.com/our-api)
- Conflict: one search snippet (older text) said the API is "free to use for non-commercial projects" and commercial use "requires a custom license". The current official page (above) supersedes this. — [Poly Haven API page](https://polyhaven.com/our-api); [Public-API GitHub](https://github.com/Poly-Haven/Public-API)
- The API is documented in OpenAPI 3.0 format. — [Poly Haven Dev Log #09](https://blog.polyhaven.com/?p=756)
- Community packages exist: `polydown` (PyPI) for bulk download. — [polydown on PyPI](https://pypi.org/project/polydown); [GitHub agmmnn/polydown](https://github.com/agmmnn/polydown)

**Blendkit (formerly BlenderKit)**
- blenderkit.com/docs/licenses now 301-redirects to blendkit.com. The page names the service "Blendkit (formerly BlenderKit)". — [Blendkit licenses](https://www.blendkit.com/docs/licenses/)
- Two licences: Royalty Free and CC0. "Everything you download is available for commercial use." Royalty Free allows commercial use without crediting the author. You may not resell an asset "in the same form" (as a model, asset pack or game level on a marketplace), even modified. Both licences allow selling higher-level derivative works (e.g. a rendered film). — [Blendkit licenses](https://www.blendkit.com/docs/licenses/)
- The licence page does not say which assets are free vs Full Plan, and says nothing about API/add-on scripted use or AI training. — [Blendkit licenses](https://www.blendkit.com/docs/licenses/)

**Sketchfab: licences**
- Free downloadable models carry either a Standard License or a Creative Commons licence. CC licences require credit except CC0. Models downloaded under the Standard licence need no credit. — [Sketchfab Help: crediting users](https://help.sketchfab.com/en/articles/16152215-crediting-users-for-3d-model-downloads); [Sketchfab Help 16152217](https://help.sketchfab.com/en/articles/16152217); [Sketchfab Help 16152220](https://help.sketchfab.com/en/articles/16152220)
- Sketchfab says "the vast majority" of downloadable models are CC BY. Sample credit line: "This work is based on Model 2 by Sketchfab licensed under CC BY 4.0". The download pop-up has a button that copies a formatted credit. — [Sketchfab blog: 600,000 free models](https://sketchfab.com/blogs/community/600000-free-3d-models-on-sketchfab); [Sketchfab: Intro to CC licenses](https://sketchfab.com/blogs/community/an-introduction-to-creative-commons-licenses)
- If a creator later changes a model's licence, the licence you downloaded it under still applies. — [Sketchfab Help 16152215](https://help.sketchfab.com/en/articles/16152215-crediting-users-for-3d-model-downloads)
- Sketchfab added licence filters to downloadable-model search. — [Sketchfab blog: license filters](https://sketchfab.com/blogs/community/refine-downloadable-model-searches-with-new-license-filters)
- Paid-asset licences on sketchfab.com/licenses: Standard (royalty-free, non-exclusive; modify and incorporate allowed; no standalone resale or sublicensing; may NOT be used "to promote alcohol, tobacco, gambling, weapons, or explosives"; credit only in AV productions where other providers are credited, suggested form "[Video/Imagery] supplied by [Licensor]"). Editorial: only for works that comment on newsworthy or public-interest subjects, "such as news articles, critical reviews, or documentaries"; no commercial/promotional use; only cropping or technical edits. — [Sketchfab Licenses](https://sketchfab.com/licenses)

**Sketchfab: Download API**
- Downloads require the end user to be authenticated with a Sketchfab account; the app must let users log in (OAuth2 linked). Apps needing downloads without end-user login must contact Sketchfab. — [Sketchfab Download API](https://sketchfab.com/developers/download-api)
- Formats via API: glTF, GLB, USDZ only. "Models are not currently available in their source formats such as FBX and OBJ through the API." — [Sketchfab Download API](https://sketchfab.com/developers/download-api)
- The page claims over 1 million free CC-licensed models, "many" commercial-OK. It does not document endpoint paths, URL expiry, search filter parameter names or rate limits. — [Sketchfab Download API](https://sketchfab.com/developers/download-api)

**Sketchfab: platform status 2024-2026**
- At Fab launch (22 Oct 2024) the Sketchfab Store closed; all purchases and sales moved to Fab. — [Wikipedia: Sketchfab](https://en.wikipedia.org/wiki/Sketchfab); [Sketchfab: what you need to know now that Fab's live](https://sketchfab.com/blogs/community/sketchfab-update-what-you-need-to-know-now-that-fabs-live/)
- Sketchfab said free and view-only models "will remain where they are". It also said it would give "plenty of notice before free downloadable content is no longer supported", implying free downloads would eventually end. — [Sketchfab: what you need to know now that Fab's live](https://sketchfab.com/blogs/community/sketchfab-update-what-you-need-to-know-now-that-fabs-live/); [Fabbaloo: Epic phases out Sketchfab in 2025](https://www.fabbaloo.com/news/epic-games-phases-out-sketchfab-in-2025-launches-unified-fab-marketplace)
- A change.org petition (advocacy, not official) says the Fab migration "rejects many Creative Commons licenses, like CC0". — [change.org petition](https://www.change.org/p/keep-sketchfab-alive-preserve-open-access-to-3d-art-museum-collections)
- Wikipedia states KitBash acquired Sketchfab (and ArtStation) on 12 Aug 2026 and lists Sketchfab as "Active". No deal details. — [Wikipedia: Sketchfab](https://en.wikipedia.org/wiki/Sketchfab)

**Sketchfab: Vietnam-era vehicle examples found**
- "Bell UH-1N Twin Huey" by helijah, listed under CC Attribution. The UH-1N is a 1969 twin-engine variant, not the UH-1D/H typical of Vietnam. — [Sketchfab model 90bf99ba…](https://sketchfab.com/3d-models/90bf99ba20f948a9838623311bd83da3)
- A photogrammetry scan of a museum UH-1 that served in Vietnam is a paid Standard-licence item (~USD 1,500 per the search snippet). Fab Huey listings are paid. — [Fab listing](https://www.fab.com/listings/cb1e2857-1c01-4242-860e-59b7e282cf6d); [stlfinder mirror of Sketchfab scan](https://stlfinder.com/model/light-switch-remote-holder/1705906)

**Fab / Quixel Megascans**
- From Fab launch until end of 2024, Megascans were free for everyone under Fab's Standard License for all engines and tools. From 2025 "the majority of Megascans will no longer be available for free", though some assets stay free. — [Unreal Engine blog: Fab launches](https://www.unrealengine.com/blog/fab-epics-new-unified-content-marketplace-launches-today); [Unreal forum: legacy Megascans](https://forums.unrealengine.com/t/access-legacy-megascans-on-bridge-and-quixel-com/2142664)
- Content acquired on Fab, free or paid, can be used forever. — [CGPress](https://cgpress.org/archives/quixel-offers-perpetual-access-to-the-entire-existing-megascans-library-with-a-single-click.html)
- Assets claimed on Quixel.com/Bridge before the switch fall under the Epic Content License as a frozen "legacy Megascans library" with no updates. — [Unreal forum: legacy Megascans](https://forums.unrealengine.com/t/access-legacy-megascans-on-bridge-and-quixel-com/2142664)
- Fab offers Creative Commons listings and a Standard License with Personal and Professional tiers, covering commercial and personal projects. — [Unreal Engine blog: Fab launches in October](https://www.unrealengine.com/blog/fab-content-marketplace-launches-in-october-publishing-portal-opens-today); [CG Channel](https://www.cgchannel.com/?p=161277)

**Smithsonian Open Access / 3D**
- Thousands of Smithsonian 3D objects can be downloaded. Items marked CC0 "are yours to take and remix". — [Smithsonian 3D: Open Access highlights](https://3d.si.edu/collections/openaccesshighlights); [si.edu 3D objects spotlight](https://www.si.edu/spotlight/3d-objects)
- Objects not marked CC0 need written permission from the institution for commercial use. Downloads come as OBJ or glTF. — [Digital Production, 2020](https://digitalproduction.com/2020/03/04/open-access-mehr-als-2000-3d-modelle/)
- The NASM collection page shows only a tiny aircraft 3D set ("Aircraft 2" filter). CC0 aircraft records found (Wright Model D, Curtiss) are physical models with photos, not confirmed 3D downloads. — [3d.si.edu Open Access highlights](https://3d.si.edu/collections/openaccesshighlights); [si.edu Wright Model D record](https://www.si.edu/object/model-static-wright-model-d%3Anasm_A19590028000)

**NASA**
- NASA content is "generally … not subject to copyright in the United States". NASA "should be acknowledged as the source". The NASA insignia and logotype "are not in the public domain". No implied endorsement of commercial products. Editorial use in non-promotional published works is generally allowed. Third-party material posted by NASA needs the rights holder's permission. — [NASA images & media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)

**Objaverse / Objaverse-XL**
- Dataset as a whole is ODC-By v1.0. Individual objects carry their own licences. Polycam-sourced data is only for approved academic non-commercial use. — [HF: allenai/objaverse-xl](https://huggingface.co/datasets/allenai/objaverse-xl)
- Objaverse 1.0 per-object breakdown: CC-BY 4.0 (721K), CC-BY-NC 4.0 (25K), CC-BY-NC-SA 4.0 (52K), CC-BY-SA 4.0 (16K), CC0 (3.5K). Metadata gives each object's licence. — [Objaverse docs](https://objaverse.allenai.org/docs/intro); [objaverse on PyPI](https://pypi.org/project/objaverse/0.0.4)

### Inferences
- Default licence policy: allow CC0, Royalty-Free (Blendkit) and CC BY / CC BY-SA (keep credit lines). Reject NC, ND and Sketchfab "Editorial" for anything that may be published commercially, and log every asset's licence at download time, because Sketchfab honours the licence you downloaded under.
- CC BY-SA on a model used inside a rendered film probably does not force the film itself under SA (the film is a collective/adapted work only in a contested sense). Prefer CC BY or CC0 to avoid the argument. This is a legal judgment, not verified.
- The Sketchfab Standard licence ban on using assets "to promote … weapons" does not obviously cover a historical documentary. Editorial licence explicitly lists documentaries, but bars commercial or promotional use.
- Objaverse 1.0 objects are Sketchfab uploads, so Objaverse is mainly useful as an offline licence-filterable index (its metadata has a per-object licence field). It is not a separate legal source. The Python package `objaverse` can pull annotations and filter by licence. Usage not verified.
- Expect few or no CC0 Vietnam-war vehicles from Smithsonian or NASA. Military vehicles (B-52, MiG-21, F-4, UH-1H, T-54/55, PT-76, M113, Mi-8) will realistically come from Sketchfab CC BY, Blendkit, or paid Fab/CGTrader models, or be self-modelled.
- From prior knowledge, unverified this session: Sketchfab Data API v3 search `GET https://api.sketchfab.com/v3/search?type=models&q=…&downloadable=true&license=<slug>` and download `GET /v3/models/{uid}/download` (returns short-lived signed URLs for gltf/glb/usdz). Check against https://docs.sketchfab.com/data-api/v3/ before coding.
- Blender 5.2 imports glTF/GLB natively (`bpy.ops.import_scene.gltf`), so Sketchfab's API format limit is not a blocker for headless pipelines.

### Gaps
- Individual Sketchfab licence checks for B-52, MiG-21, F-4, T-54/T-55, M113, PT-76 and Mi-8 were not done. Only the UH-1N was confirmed CC BY. Needs a scripted search with licence filters.
- Whether Sketchfab free downloads and the Download API still work after the reported Aug 2026 KitBash acquisition: no primary source found.
- Fab EULA text (fab.com/eula returned 403): exact Personal vs Professional threshold, AI/generative-AI clauses, and whether free Megascans can be used outside Unreal. Not verified.
- Smithsonian terms page (si.edu/termsofuse) returned 403. CC0 statement came via 3d.si.edu snippets and a 2020 secondary article.
- NASA 3D Resources catalogue contents and licence page not fetched. Only the general NASA media guidelines were verified.
- No open museum 3D scan collection of Vietnam-war vehicles was found (e.g. Imperial War Museums, Vietnam Military History Museum).

---

## 2. Period satellite imagery: declassified CORONA, KH-7, KH-9 (USGS)

### Takeaway
USGS declassified imagery is federally created, public domain, and free to download where already scanned. Unscanned frames cost about $30/frame to scan on demand. Resolution is ~40 ft (KH-1, 1960) to ~6 ft (KH-4B, 1967-72) for CORONA, 20-30 ft for the KH-9 mapping camera, and 2-4 ft for the KH-9 panoramic camera. Scans are not geocorrected, so georeferencing is real work. University of Edinburgh has already published CC BY 4.0 georeferenced KH-9 tiles of Quang Tri and the Vietnam-Laos-Cambodia tri-border (1972-73). Programmatic access is via the USGS M2M JSON API, which needs an approved account.

### Cited Findings
- CORONA ground resolution per USGS archive table: KH-1 (Aug 1960) 40 ft; KH-4A (Aug 1963-Sep 1969) 9 ft; KH-4B (Sep 1967-May 1972) 6 ft. — [USGS Declassified Satellite Imagery-1](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-declassified-data-declassified-satellite-imagery-1) (via search snippet; page JS-rendered)
- More than 860,000 images collected 1960-1972 were declassified in 1995. — [USGS Declass-1 (on.doi.gov)](https://on.doi.gov/3hpEfqf); [data.gov.uk KH-4B record](https://www.data.gov.uk/dataset/c50f598f-d6f3-4b48-ab80-13663a033a37/kh-4b-corona-satellite-panchromatic-image-for-a-partial-area-extending-across-the-syrian-and-tu). An older government document gives per-mission frame counts (e.g. KH-4B 188,526; KH-4A 517,688) that are not reconciled with the 860k figure — [govdocs PDF](https://corpora.tika.apache.org/base/docs/govdocs1/710/710965.pdf)
- EarthExplorer can search, preview and download existing digital files at no cost. CORONA digital products are 7- or 14-micron scans, and "the scanning process does not apply geocorrections". — [USGS Declass-1](https://www.usgs.gov/index.php/centers/eros/science/usgs-eros-archive-declassified-data-declassified-satellite-imagery-1) (via search snippet)
- Declass-2 (KH-7 GAMBIT, KH-9 HEXAGON mapping camera): the KH-9 mapping camera gives 9 x 18 inch film frames at 20-30 ft ground resolution. High-resolution scans are $30.00 per frame, on photogrammetric scanners at 7 or 14 microns. Already-digitized images download free; un-scanned film needs a $30/frame order. — [USGS Declass-2](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-declassified-data-declassified-satellite-imagery-2) (via search snippet); [Frontiers in Earth Science 2020](https://www.frontiersin.org/articles/10.3389/feart.2020.566802/pdf)
- Declass-3 (2013) is a USGS subset of KH-9 HEXAGON panoramic-camera missions, 1971-1984, "high resolution (2-4 feet)". Availability is "primarily over the United States, Antarctica, and the Arctic Circle". — [data.gov: Declass 3](https://catalog.data.gov/dataset/declass-3-2013-usgs-subset-of-hexagon-missions-kh-9-1971-1984); [USGS Declass-3](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-declassified-data-declassified-satellite-imagery-3)
- Contradicting the "primarily US" note: University of Edinburgh published georeferenced KH-9 imagery from Nov 1972 covering parts of Cambodia, Laos and Vietnam (tri-border), and from March 1973 covering parts of Viet Nam and Lao PDR (Quang Tri mosaic). Originals come from USGS Declassified Satellite Imagery-3. The tri-border dataset is CC BY 4.0. — [Edinburgh DataShare: Tri-border](https://datashare.ed.ac.uk/handle/10283/8722); [Edinburgh DataShare: Quang Tri](https://datashare.ed.ac.uk/handle/10283/8721); [Edinburgh Research Explorer](https://www.research.ed.ac.uk/en/datasets/georeferenced-kh-9-imagery-tri-border-area/)
- The same researcher (Philipp Barthelme) used HEXAGON and CORONA imagery to map Vietnam-war bomb craters and herbicide spray lines, which "appear in the black and white photos quite clearly". — [USGS Eyes on Earth Ep. 133: Vietnam War Bomb Craters](https://www.usgs.gov/media/audio/eyes-earth-episode-133-vietnam-war-bomb-craters)
- Rights: "most of the images, data, and related products available from the USGS EROS Center are federally created data and therefore reside in the public domain". USGS asks for credit, e.g. "… image courtesy of the U.S. Geological Survey". — [USGS EROS data citation](https://www.usgs.gov/centers/eros/data-citation)
- M2M API: a RESTful JSON API over 300+ USGS/EROS datasets with the same functions as EarthExplorer. It returns download URLs usable with wget/cURL. — [USGS M2M](https://m2m.cr.usgs.gov/)
- M2M access must be requested on the EROS profile page, then approved. — [lsru docs](https://lsru.readthedocs.io/en/latest/generated/lsru.Usgs.login.html). Password `login` was deprecated 26 Feb 2025. Use an application token with the `login-token` endpoint — [USGS M2M application token documentation](https://www.usgs.gov/media/files/m2m-application-token-documentation)
- Dataset identifiers seen in third-party code (not confirmed in USGS docs): `corona2` (usgs-m2m-api wrapper, "early stages… not for production"); `declassii` for KH-9 (usgsxplore); default `DECLASSII` (spymicmac). — [usgs-m2m-api GitHub](https://github.com/castuofa/usgs-m2m-api); [usgsxplore PyPI](https://pypi.org/project/usgsxplore); [spymicmac USGS module](https://spymicmac.readthedocs.io/en/v0.1.1/spymicmac/modules/usgs.html)
- In EarthExplorer, choose the Declassified data sets, then Additional Criteria "Declass 1" for KH-4B, with Declass 2 as fallback. NASA Ames Stereo Pipeline documents processing KH-4B (and other historical) imagery. — [Ames Stereo Pipeline: historical imagery](https://stereopipeline.readthedocs.io/en/stable/examples/historical.html)
- CORONA Atlas (Univ. of Arkansas CAST) offers orthorectified CORONA imagery free "for non-commercial use", focused on the Middle East. — [CORONA Atlas](https://corona.cast.uark.edu/)

### Inferences
- For a Vietnam documentary, the fastest legal route to georeferenced 1972-73 frames of the DMZ / Quang Tri / tri-border (Ho Chi Minh Trail entry, Khe Sanh area) is the Edinburgh CC BY 4.0 tiles: credit Edinburgh plus USGS. Elsewhere (Hanoi, Điện Biên Phủ, Hai Phong) use raw USGS frames and georeference them with GCPs (GDAL `gdal_translate -gcp` + `gdalwarp -tps`) against Sentinel-2 or Copernicus DEM. spymicmac or Ames Stereo Pipeline can handle KH-9/KH-4B camera models if orthorectification is needed.
- CORONA has no 1945-1954 coverage. The French war (Điện Biên Phủ 1954) needs maps and aerial photos, not satellite imagery.
- Public domain covers the US-government imagery itself. Third-party derived products (CORONA Atlas, Edinburgh) carry their own licences: CORONA Atlas is non-commercial only, Edinburgh is CC BY.
- CORONA and Declass-2 frames are panoramic and distorted. A 7-micron scan of a KH-4B frame is several GB, so budget disk space (F: is nearly full per project memory).

### Gaps
- Exact Vietnam/Laos frame counts and which frames are already scanned (free) vs scan-on-demand: needs an M2M `scene-search` with a Vietnam bounding box. Not run.
- Official M2M dataset names (`corona2`, `declassii`, `declassiii`?) not confirmed in USGS documentation; the USGS pages did not render for the fetcher.
- KH-7 GAMBIT resolution and Southeast Asia coverage not retrieved.
- Edinburgh dataset file formats, sizes and georeferencing accuracy not retrieved (403).
- Current scan-on-demand turnaround time and whether the $30 price still holds in 2026 not confirmed.

---

## 3. Period maps: US Army Map Service, French Indochina, Soviet

### Takeaway
US AMS L7014 1:50,000 (1964-71) sheets are widely scanned. ANU's Open Research repository marks them "Copyright Expired" and offers free JPG + ~100 MB TIFF downloads. ANU also holds many Service Géographique de l'Indochine 1:100,000 "Carte de l'Indochine" sheets (1904-1952), but leaves the licence field blank. UT Austin PCL hosts L7014 too, but blocks automated fetches with a bot wall. David Rumsey items are CC BY-NC-SA, and Gallica charges for commercial reuse. Soviet maps have no clear legal status and are only sold as reprints.

### Cited Findings
- UT Austin PCL lists "1:50,000 - Vietnam, Series L7014 (Topographic Maps) U.S. Army Map Service, 1964-1971", plus a GeoPDF version covering most of northwest Vietnam. — [Mirror of UT PCL Vietnam page (366thgunfighters.org)](https://www.366thgunfighters.org/university-of-texas---maps-of-vietnam.html)
- maps.lib.utexas.edu (both the Vietnam AMS page and the FAQ) returned an Anubis "Access Denied" bot-protection page to automated fetches. — [UT PCL Vietnam AMS](https://maps.lib.utexas.edu/maps/ams/vietnam/); [UT PCL FAQ](https://maps.lib.utexas.edu/faq.html)
- The OSM wiki describes the PCL collection as containing many public-domain topographic maps. — [OSM wiki: PCL Map Collection](https://wiki.openstreetmap.org/wiki/Perry-Casta%C3%B1eda_Library_Map_Collection)
- ANU Open Research holds individual L7014 sheets (e.g. Son Tay 6151 III 1967; Soprai 6631 I 1966, "prepared by AMS and printed in Vietnam"), each open access with rights "Copyright Expired". — [ANU: Son Tay L7014](https://openresearch-repository.anu.edu.au/items/c6c29b02-131a-4f62-b8fb-9615e6d1321b/full); [ANU: Soprai L7014](https://dspace-prod.anu.edu.au/items/7815224f-45aa-48ef-b385-86ba2933aeee/full); [ANU: Pa Kha L7014](https://openresearch-repository.anu.edu.au/items/3d217c68-ab7d-4eed-849e-a61b2366a4f9/full)
- ANU holds "Carte de l'Indochine" 1:100,000 sheets published in Hanoi by the Service Géographique de l'Indochine, e.g. Mon-Cay 1950 (sheet 40 W), Cam-Pha 1950, Son-Tay 1949, Ninh-Binh 1949, Dinh Lap 1952, Phu Nho Quan 1951, Bac-Ninh 1904, Nam-Dinh 1910, Phat-Diem 1912. — [ANU search results, e.g. Mon-Cay](https://openresearch-repository.anu.edu.au/handle/1885/136721); [ANU Ninh-Binh 1949](https://openresearch-repository.anu.edu.au/items/05028f37-82eb-41da-a07b-6665942e9b28); [ANU Dinh Lap 1952](https://openresearch-repository.anu.edu.au/items/c35929ce-cc0f-46ac-9298-e7dbdf4dac55)
- Mon-Cay 1950 record: collection VNM03 1:100 000 (ANU Asia-Pacific Map Collection), "Open Access", "License Rights" field blank. Files: JPG master 10.3 MB and TIFF preservation copy 103.12 MB. An End User Agreement is linked but not shown. — [ANU Mon-Cay 1950](https://openresearch-repository.anu.edu.au/handle/1885/136721)
- ANU also has an index for "Carte routière de l'Indochine" 1:400,000, 1945-1951. — [ANU Digital Collections](https://digitalcollections.anu.edu.au/items/b4384e16-6c4f-4c61-96dd-bb824dbafe7c/full)
- Texas Tech Vietnam Center (Virtual Vietnam Archive) holds L7014 sheets in the Richard (Dick) Detra Collection, e.g. An Loc 1:50,000, 1 Dec 1968. Each record gives a "Pub Credit Line" ("… Vietnam Center and Sam Johnson Vietnam Archive, Texas Tech University"). — [TTU VVA digital object 635103](https://vva.vietnam.ttu.edu/repositories/2/digital_objects/635103). The archive aims to put "all non-copyrighted materials" online. Explicit reuse terms not found — [TTU Map Search PDF](https://museum.vhpa.org/images/TTU%20Map%20Search.pdf)
- David Rumsey: an example Indochina item (1780 Bonne) is CC BY-NC-SA 3.0 Unported. GeoTIFF download on the Rumsey Georeferencer needs sign-in. — [DigitalPasifik/DPLA record](https://digitalpasifik.org/items/469488); [Rumsey Georeferencer 1939 Indochine map](https://davidrumsey.georeferencer.com/maps/7bae8a11-132a-40e0-9764-a3a3a606c066/)
- Gallica/BnF: non-commercial reuse "libre et gratuite" with source credit. Commercial reuse "payante et fait l'objet d'une licence". High-resolution files for commercial use via reutilisationcommerciale@bnf.fr. Use abroad is subject to that country's law. BnF's ownership claim over reproductions of public-domain works is contested. — [linuxfr: Gallica conditions](https://linuxfr.org/users/pamputt/journaux/conditions-d-utilisation-des-contenus-de-gallica); [Assemblée nationale QE 23878](https://questions.assemblee-nationale.fr/dyn/14/questions/QANR5L14QE23878.pdf); [ActuaLitté](https://actualitte.com/article/57529/archives/la-bnf-en-flagrant-delit-de-copyfraud-une-deputee-alerte-aurelie-filippetti)
- Soviet/Vietnamese maps: North Vietnam was mapped to Russian specifications by the National Administration of Geodesy and Cartography, including at 1:100,000. French 1:100,000 coverage was revised in the early 1950s. — [geospatial.com Vietnam profile](https://geospatial.com/country_profiles/vietnam/). Longitude Maps sells print reproductions of Soviet military city plans (1:10,000) for Hanoi, Saigon, Hue and Haiphong — [Longitude Maps: Hanoi 2](https://www.longitudemaps.com/products/hanoi-2-vietnam-soviet-military-city-plans_suaa-hanoi2)

### Inferences
- AMS maps are US federal works, so they are public domain under 17 U.S.C. §105. This is consistent with ANU's "Copyright Expired" label but was not verified on a US government page this session. Recommended credit: "U.S. Army Map Service, Series L7014, sheet XXXX, 1966; scan: ANU Open Research / UT Libraries".
- French SGI sheets from about 1950 are French state collective works. The roughly 70-years-after-publication term would have lapsed for most pre-1955 sheets. This is a legal inference, not verified; ANU gives no licence. Treat ANU scans as low risk but credit "Service Géographique de l'Indochine, ANU Asia-Pacific Map Collection".
- Georeferencing: L7014 sheets are on a UTM grid (Indian 1960 / Everest datum per common knowledge, unverified). Corner coordinates can be set as GCPs and warped with GDAL. The UT GeoPDF version for northwest Vietnam is already georeferenced, which saves effort if it can be fetched manually.
- For scripting, ANU's DSpace (REST/OAI-PMH) is the most automatable map host found. UT PCL's bot wall means downloading by hand, or asking the owner to fetch.
- Do not use David Rumsey or Gallica scans in a monetised film without paying or confirming. Both carry non-commercial limits.

### Gaps
- UT PCL copyright/permission wording and scan resolution: could not fetch (bot wall).
- Whether Gallica holds SGI 1:25,000 / 1:100,000 Indochina series: no Gallica record found in search.
- EFEO / CNRS / IGN (France) digitised Indochina map holdings and their licences: not researched (call budget).
- L509 (1:250,000) and L605 / L7015 series availability: not confirmed.
- Soviet General Staff maps of Vietnam: no free source with clear rights found. Russian state map copyright status unknown.
- ANU End User Agreement text (governs reuse) not read.

---

## 4. Elevation data: which DEM for 30 m Blender terrain

### Takeaway
Copernicus GLO-30 is the best default. It is free, allows reproduction, distribution and adaptation (no non-commercial limit), and sits on AWS as COGs with no AWS account needed. It needs a fixed attribution notice and a liability sentence. It is a DSM (includes canopy and buildings), which for jungle terrain inflates heights. AW3D30 v4.1 (JAXA, free commercial with registration) is the alternative. FABDEM (bare earth) is CC BY-NC-SA, so not for commercial films. No open DEM finer than 30 m for Vietnam was found.

### Cited Findings
- Copernicus DEM on AWS: GLO-30 Public `arn:aws:s3:::copernicus-dem-30m` and GLO-90 `arn:aws:s3:::copernicus-dem-90m`, eu-central-1, COG format. STAC: copernicus-dem-30m-stac.s3.amazonaws.com and copernicus-dem-90m-stac.s3.amazonaws.com. Public access with `aws s3 ls --no-sign-request s3://copernicus-dem-30m/`. It is a Digital Surface Model ("including buildings, infrastructure, and vegetation") from the 2021 release. No ocean tiles (assume 0). Some countries' GLO-30 tiles are not public (list in a linked spreadsheet). Readme: https://copernicus-dem-30m.s3.amazonaws.com/readme.html — [AWS Registry: Copernicus DEM](https://registry.opendata.aws/copernicus-dem/)
- Copernicus WorldDEM-30 licence (verified from the PDF text):
  - Art. 4 grants worldwide, unlimited-time, non-exclusive rights of "(a) reproduction; (b) distribution; (c) communication to the General Public; (d) adaptation, modification and combination with other data". Art. 5: free of charge.
  - Art. 6(a): when distributing or showing it publicly, use the notice "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved."
  - Art. 6(b): if adapted, use "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved".
  - Art. 6(c): add "The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30".
  - Art. 6(d): don't imply endorsement.
  - The higher-resolution WorldDEM-10 is excluded from public distribution.
  — [License-COPDEM-30.pdf](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf)
- The TanDEM-X 30 m Edited DEM (DLR) is different: free only for non-commercial and scientific use, with a separate commercial licence to buy. — [DLR TanDEM-X 30m EDEM licence](https://geoservice.dlr.de/resources/licenses/tdm30-edited/License_for_the_Utilization_of_TanDEM-X_30m-EDEM_DCM_for_Scientific_Use.pdf)
- AW3D30 (JAXA): "Any of the commercial and non-commercial purposes can be used free of charge" under JAXA's Terms for Use (https://earth.jaxa.jp/policy/en.html). Version 4.1 released April 2024 (global except Japan and Antarctica, 19,051 tiles), ~1 arc-second. Download needs registration and email activation; files are 1x1° or 5x5° ZIPped GeoTIFF. Black areas are no-data (cloud/snow/ice). — [JAXA AW3D30](https://www.eorc.jaxa.jp/ALOS/en/dataset/aw3d30/aw3d30_e.htm). Credit wording "Courtesy of the Japan Aerospace Exploration Agency (JAXA)" appears in a DLR document (secondary) — [DLR licence PDF](https://geoservice.dlr.de/resources/licenses/tdm30-edited/License_for_the_Utilization_of_TanDEM-X_30m-EDEM_DCM_for_Scientific_Use.pdf). Earth Engine has `JAXA/ALOS/AW3D30/V4_1` — [GEE catalog](https://developers.google.com/earth-engine/datasets/catalog/JAXA_ALOS_AW3D30_V2_1)
- FABDEM (bare-earth, from Copernicus GLO-30): CC BY-NC-SA 4.0, non-commercial ShareAlike. Users must include the Copernicus attribution. — [GEE community catalog: FABDEM](https://gee-community-catalog.org/projects/fabdem/). Conflict: the University of Bristol "FABDEM Vietnam" dataset page reportedly lists CC BY 4.0. Page fetch failed (ECONNRESET), not verified — [data.bris: FABDEM Vietnam](https://data.bristol.ac.uk/data/dataset/20egxk888rljr25vst4u3nhnyz)
- NASADEM_HGT: 1 arc-second, reprocessed from SRTM telemetry (NASA + NGA). Catalog pages don't state a licence. LP DAAC citations are product-specific via DOI. — [Earthdata: NASADEM_HGT](https://www.earthdata.nasa.gov/es/data/catalog/lpcloud-nasadem-hgt-001?page=1%2C0); [USGS EROS data citation](https://www.usgs.gov/centers/eros/data-citation)
- Most USGS EROS products are federally created and public domain. — [USGS EROS data citation](https://www.usgs.gov/centers/eros/data-citation)

### Inferences
- Pipeline suggestion: STAC or direct S3 read of Copernicus GLO-30 COG tiles with `rasterio` / `rio-cogeo`, mosaic and reproject to UTM 48N with GDAL, write a 16-bit heightmap or mesh into Blender. No credentials needed. Tile naming (from prior knowledge, unverified): `Copernicus_DSM_COG_10_N21_00_E105_00_DEM/…tif`. Check the readme.
- Jungle canopy (often 20-40 m) is baked into a DSM. For hero close-ups of mountain valleys (Điện Biên Phủ basin, Khe Sanh, Trường Sơn), heights will look slightly blunted. FABDEM fixes this but is non-commercial. For a commercial release, use GLO-30 and accept canopy, or smooth/offset it manually.
- Vietnam is presumably in the public GLO-30 set (to my knowledge the withheld tiles are Armenia and Azerbaijan), but confirm against the spreadsheet linked from the AWS page.
- For 1960s-accurate terrain, modern DEMs are fine (landforms barely changed). Exceptions are reservoirs built after 1975 (e.g. Hòa Bình 1979-94, Sơn La) that flooded valleys, so period shots of those valleys need manual water masking.
- SRTM v3 / NASADEM (public domain, NASA/USGS) are licence-simplest fallbacks if attribution text must be minimal. Access is via NASA Earthdata login. Not verified this session.

### Gaps
- No open DEM finer than 30 m for Vietnam found (national 1:10,000/1:25,000 contour data from MONRE is not open, per lack of sources).
- JAXA Terms for Use page (earth.jaxa.jp/policy) not read verbatim; exact credit wording comes from a secondary source.
- FABDEM licence conflict (CC BY-NC-SA vs Bristol Vietnam page CC BY 4.0) unresolved. FABDEM v1-2 on the Bristol data portal should be checked by hand.
- NASADEM / SRTM v3 explicit licence statement not retrieved.
- OpenTopography API (needs an API key) as a single endpoint for all of these: not researched.

---

## 5. Modern imagery for terrain textures (beyond EOX Sentinel-2 cloudless 2016)

### Takeaway
Raw Sentinel-2 L2A (Copernicus terms: free, commercial OK, credit "Contains modified Copernicus Sentinel data [Year]") and Landsat (public domain) are the clean choices. Build your own cloud-free composite from STAC (AWS Earth Search). EOX cloudless is CC BY-NC-SA for non-commercial use; commercial use needs an EOX licence. Google Earth/Earth Studio footage may be used in documentaries with on-screen attribution, but Photorealistic 3D Tiles forbid caching and extraction, so importing them into Blender for a rendered film is not permitted. Esri World Imagery is under the Esri Master Licence and not meant for offline export.

### Cited Findings
- EOX cloudless licence summary: non-commercial use free under CC BY-NC-SA 4.0. Commercial use needs the "EOX Commercial Attribution-RestrictedUse 1.2 License". Attribution is required everywhere imagery appears (credits/metadata if on-image impossible) and must include "Contains modified Copernicus Sentinel data <year>". No sub-licensing or resale without a separate agreement. — [EOX cloudless licence](https://cloudless.eox.at/documentation/license)
- s2maps.eu now 301-redirects to cloudless.eox.at. Products are 10 m: Viewing Basic (tiled GeoTIFF / WMTS, 8-bit RGB, EPSG:4326/3857, zoom 0-13/14), Viewing Ready (GeoPackage), Exploitation Starter/Ready (scaled / 12-bit reflectance), sold via "Buy now"/"Contact sales". — [EOX product list](https://cloudless.eox.at/documentation/product-list)
- Conflict: the fetched EOX pages do not list a per-year licence and did not confirm "2016 = CC BY 4.0". The task premise (2016 CC BY 4.0, later years CC BY-NC-SA) could not be verified on the current site. — [EOX cloudless licence](https://cloudless.eox.at/documentation/license)
- Copernicus Sentinel data legal notice: free, full and open access. Permitted: reproduction, distribution, communication to the public, adaptation, modification, combination. Notice "Copernicus Sentinel data [Year]" or "Contains modified Copernicus Sentinel data [Year]". — [Sentinel data legal notice (BKG copy, German)](https://sg.geodatenzentrum.de/web_public/gdz/lizenz/deu/sentinel_data_legal_notice_deu.pdf); [Debian copyright quoting the notice](https://metadata.ftp-master.debian.org/changelogs/main/s/sarsen/stable_copyright); [USGS Sentinel-2 Terms](https://www.usgs.gov/media/files/sentinel-2-terms-and-conditions)
- Sentinel-2 L2A COGs on AWS Open Data. The Earth Search STAC collection `sentinel-2-l2a` (Element 84) is in bucket `e84-earth-search-sentinel-data`. Citation format "Sentinel-2 Cloud-Optimized GeoTIFFs was accessed on DATE from https://registry.opendata.aws/sentinel-2-l2a-cogs". — [AWS Registry: sentinel-2-l2a-cogs](https://registry.opendata.aws/sentinel-2-l2a-cogs/); [Element84 earth-search GitHub](https://github.com/Element84/earth-search)
- Landsat/USGS EROS data are public domain. Credit e.g. "Landsat-7 image courtesy of the U.S. Geological Survey". — [USGS EROS data citation](https://www.usgs.gov/centers/eros/data-citation)
- Google Earth / Earth Studio:
  - Content "can be used for purposes such as research, education, film and nonprofit use without needing permission", including TV, films, documentaries and monetised educational/entertainment online video. Promotional or commercial uses (ads, promo films, business-promoting documentaries) are not covered.
  - You may not "significantly alter our imagery without providing clear context that it's a simulation", nor use output "to reconstruct 3D models".
  - Attribution must stay on screen with the content ("You may not move the attribution away from the content", including to the film credits) and must name Google plus data providers as displayed.
  — [Google Geo Guidelines](https://about.google/brand-resource-center/products-and-services/geo-guidelines/)
- Google Photorealistic 3D Tiles (Map Tiles API) policies:
  - "you must not pre-fetch, index, store, or cache any Content" except as the terms allow. No offline use.
  - Your own 3D objects must not be "extracted, traced, or otherwise derived … from Photorealistic 3D Tiles".
  - All tile attributions (from the glTF `asset.copyright` field) plus the Google Maps logo must be shown, and the logo must not be obscured.
  - Video is addressed only for ≤30 s promotional videos about your application.
  — [Map Tiles API policies](https://developers.google.com/maps/documentation/tile/policies)
- Esri World Imagery: licensed under the Esri Master License Agreement. The layer "is not intended to be used to export tiles for offline"; a separate "World Imagery (for Export)" layer exists for offline use in ArcGIS apps. The credit string lists Esri, DigitalGlobe, GeoEye, i-cubed, USDA FSA, USGS, AEX, Getmapping, Aerogrid, IGN, IGP, swisstopo, GIS User Community. Apps must show "Powered by Esri". — [Esri World Imagery item](https://goto.arcgis.com/maps/World_Imagery); [Esri support 000012040](https://support.esri.com/Technical-Article/000012040); [Esri basemap attribution](https://Developers.arcgis.com/documentation/mapping-apis-and-services/deployment/basemap-attribution/)

### Inferences
- Best legal texture path for Blender: query Earth Search STAC (`pystac-client`, collection `sentinel-2-l2a`, filter `eo:cloud_cover`), build a median composite of the visual or B04/B03/B02 bands with `stackstac`/`odc-stac` + `rioxarray` (library names from prior knowledge, unverified here), color-grade it, and drape it on the GLO-30 mesh. Credit "Contains modified Copernicus Sentinel data 2025" plus the Copernicus DEM notice. Vietnam's monsoon cloud cover means a multi-season median is needed.
- Google Earth Studio renders can go into the documentary as separate shots with on-screen attribution, if the film is not promotional. Pulling Google 3D Tiles into Blender (e.g. with add-ons that cache tiles) conflicts with the no-caching and no-derivation rules. Avoid it for anything published.
- Esri imagery is not cleared for video use by any page found. Treat it as not usable without asking Esri.
- 10 m Sentinel-2 is soft for low-altitude shots. Below about 1-2 km camera altitude, detail must come from procedural/Poly Haven ground textures blended over the satellite color.

### Gaps
- Mapbox Satellite terms for video/offline use: not researched (call budget).
- EOX per-year licence history (2016 CC BY vs later NC-SA) and commercial prices: not confirmed on current pages.
- Official Copernicus legal-notice page (European Commission) not fetched directly; wording verified via BKG copy and Debian quotation.
- Bing/Maxar or Planet NICFI tropical basemaps (NICFI covers tropics, including Vietnam?) not researched.

---

## 6. HDRI, sky and atmosphere assets for realistic lighting

### Takeaway
Poly Haven HDRIs (CC0, scriptable API, no attribution needed for the assets) are the primary source. ambientCG is a second CC0 source, licence confirmed only via secondary sites. Blender's built-in procedural sky avoids licensing entirely.

### Cited Findings
- Poly Haven HDRIs are CC0, free for commercial use with no attribution required. The API needs only a unique User-Agent and is free including commercial use. — [Poly Haven License](https://polyhaven.com/license); [Poly Haven API](https://polyhaven.com/our-api)
- Poly Haven downloads are offered at multiple resolutions (1k-24k for HDRIs) and formats (EXR/HDR/JPG/PNG/blend/FBX/glTF/USD) per a community scraper listing. — [Apify Poly Haven scraper](https://apify.com/crawlerbros/polyhaven-scraper)
- ambientCG: CC0 PBR materials, textures and HDRIs up to 8K, no attribution required. A guide says it has a free no-key API. Secondary sources only. — [licenseorg: ambientCG](https://licenseorg.com/guide/3d-assets/ambientcg); [Cinevva guide 2026](https://app.cinevva.com/guides/free-textures-hdris-materials)

### Inferences
- For period war scenes (overcast monsoon skies, smoke, dusk raids), choose Poly Haven HDRIs by tag via API (`/assets?t=hdris&c=overcast` style categories, unverified parameter names) and cache locally. Blender's Sky Texture node (Nishita physical sky in 4.x; confirm the name/availability in 5.2) plus volumetric fog avoids any licence question. Neither was verified this session.
- Do not use Poly Haven's example renders or logos (not CC0).

### Gaps
- ambientCG's own licence page and API documentation not fetched.
- No research done on other HDRI sources (e.g. HDRI-Skies, iHDRI) or on licensed sky-timelapse plates.
- Blender 5.2 built-in sky/atmosphere features not verified.
