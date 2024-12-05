import ee
import geemap
import logging
import multiprocessing
import os
import requests
import shutil
from retry import retry

ee.Initialize(opt_url="https://earthengine-highvolume.googleapis.com")

@retry(tries=10, delay=1, backoff=2)
def getResult(index, item,*,region, image, params):
    
    point = ee.Geometry.Point(item["coordinates"])
    region = point.buffer(params["buffer"]).bounds()

    if params["format"] in ["png", "jpg"]:
        url = image.getThumbURL(
            {
                "region": region,
                "dimensions": params["dimensions"],
                "format": params["format"],
            }
        )
    else:
        url = image.getDownloadURL(
            {
                "region": region,
                "dimensions": params["dimensions"],
                "format": params["format"],
            }
        )

    if params["format"] == "GEO_TIFF":
        ext = "tif"
    else:
        ext = params["format"]
    print("URL", url)

    r = requests.get(url, stream=True)
    if r.status_code != 200:
        r.raise_for_status()

    out_dir = os.path.abspath(params["out_dir"])
    basename = str(index).zfill(len(str(params["count"])))
    filename = f"{out_dir}/{params['prefix']}{basename}.{ext}"
    with open(filename, "wb") as out_file:
        shutil.copyfileobj(r.raw, out_file)
    print("Done: ", basename)
