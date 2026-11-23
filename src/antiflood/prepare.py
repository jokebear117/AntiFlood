"""Download the public inputs and pinned browser assets needed by the local app."""

from base64 import b64encode
from hashlib import sha512
from io import BytesIO
from pathlib import Path
from shutil import copyfileobj
from tarfile import open as open_tar
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

from dotenv import load_dotenv
from remotezip import RemoteZip

from .data import ROOT, dataset_dir

SEOUL_DOWNLOAD = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"
BRISTOL_ARCHIVE = (
    "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/N30E120-N40E130_FABDEM_V1-2.zip"
)
DEM_TILE = "N37E127_FABDEM_V1-2.tif"
MAPLIBRE_VERSION = "6.19.0"
MAPLIBRE_INTEGRITY = "3bOrnfddggUYudLGJFsYFvqulUyvSxy4iQzd/uURI7ZhgYEZifdSrECujRSghaCpc+v/ZsFI0Y6ZsGSilEtE+w=="


def save_if_missing(path: Path, source, validate=None):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Preparing {path}", flush=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
        try:
            with source() as response:
                copyfileobj(response, tmp)
            tmp.close()
            if validate:
                validate(temporary)
            temporary.replace(path)
        finally:
            tmp.close()
            temporary.unlink(missing_ok=True)
    print(f"Prepared {path}", flush=True)


def valid_zip(path):
    with ZipFile(path) as archive:
        if bad := archive.testzip():
            raise ValueError(f"Corrupt source archive member: {bad}")


def seoul_file(sequence):
    form = urlencode({"infId": "OA-1168", "infSeq": "3", "seq": sequence, "seqNo": ""}).encode()
    return urlopen(Request(SEOUL_DOWNLOAD, data=form), timeout=60)


def prepare_inputs(dataset):
    raw = dataset / "raw"
    save_if_missing(raw / "rainfall/rainfall_2022.zip", lambda: seoul_file("202214"), valid_zip)
    save_if_missing(raw / "rainfall/stations_epsg5181.zip", lambda: seoul_file("999998"), valid_zip)
    tiles = {DEM_TILE: 0xA0B509DB, "N37E126_FABDEM_V1-2.tif": 0xF4C0F290}
    for name, crc in tiles.items():
        dem = raw / "dem" / name
        if not dem.exists():
            with RemoteZip(BRISTOL_ARCHIVE, timeout=90) as archive:
                member = archive.getinfo(name)
                if member.CRC != crc:
                    raise ValueError("FABDEM tile checksum differs from the documented V1-2 input.")
                save_if_missing(dem, lambda: archive.open(member))


def prepare_maplibre():
    directory = ROOT / "web/vendor"
    assets = (
        "dist/maplibre-gl.mjs", "dist/maplibre-gl-shared.mjs",
        "dist/maplibre-gl-worker.mjs", "dist/maplibre-gl.css", "LICENSE.txt",
    )
    if all((directory / Path(name).name).is_file() for name in assets):
        return
    url = f"https://registry.npmjs.org/maplibre-gl/-/maplibre-gl-{MAPLIBRE_VERSION}.tgz"
    with urlopen(url, timeout=60) as response:
        package = response.read()
    if b64encode(sha512(package).digest()).decode() != MAPLIBRE_INTEGRITY:
        raise ValueError("MapLibre package checksum did not match.")
    with open_tar(fileobj=BytesIO(package), mode="r:gz") as archive:
        for name in assets:
            save_if_missing(directory / Path(name).name, lambda: archive.extractfile(f"package/{name}"))


def main():
    load_dotenv(ROOT / ".env")
    prepare_inputs(dataset_dir())
    prepare_maplibre()


if __name__ == "__main__":
    main()
