"""Extract a manually obtained official archive privately; no downloader/bypass."""
import argparse
import hashlib
from pathlib import Path,PurePosixPath
import shutil
import stat
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/speech-api/src"))
from speech_xray.corpus.validation import PRIVATE_ROOT
from speech_xray.corpus.pipeline import new_text
from speech_xray.acoustics.models import evidence_json


def extract(archive,output):
    archive=Path(archive).resolve();output=Path(output).resolve()
    if not archive.is_relative_to(PRIVATE_ROOT.resolve()) or not output.is_relative_to(PRIVATE_ROOT.resolve()) or output.exists():
        raise ValueError("ARCHIVE_PRIVATE_AND_OUTPUT_NEW_PRIVATE_REQUIRED")
    hasher=hashlib.sha256()
    with archive.open("rb") as stream:
        while chunk:=stream.read(1024*1024):hasher.update(chunk)
    with zipfile.ZipFile(archive) as container:
        entries=container.infolist()
        if sum(info.file_size for info in entries)>25*1024**3:raise ValueError("UNEXPECTED_ARCHIVE_SIZE")
        names=set()
        for info in entries:
            name=PurePosixPath(info.filename)
            target=(output/info.filename).resolve()
            if (name.is_absolute() or ".." in name.parts or "\\" in info.filename or ":" in info.filename
                    or not target.is_relative_to(output) or stat.S_ISLNK(info.external_attr>>16)
                    or info.filename.casefold() in names):raise ValueError("UNSAFE_OR_DUPLICATE_ARCHIVE_MEMBER")
            names.add(info.filename.casefold())
        output.mkdir(parents=True,exist_ok=False)
        for info in entries:
            target=output/info.filename
            if info.is_dir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with container.open(info) as source,target.open("xb") as destination:shutil.copyfileobj(source,destination)
    return {"source_type":"EXTERNAL_RESEARCH_CORPUS","archive_path":str(archive),"archive_sha256":hasher.hexdigest(),
            "archive_bytes":archive.stat().st_size,"output_root":str(output),"member_count":len(entries),
            "provenance_role":"OPERATOR_SUPPLIED_OFFICIAL_DISTRIBUTION_REQUIRES_SOURCE_VERIFICATION"}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",required=True,type=Path);parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--receipt",required=True,type=Path)
    args=parser.parse_args()
    try:
        receipt=args.receipt.resolve()
        if not receipt.is_relative_to(PRIVATE_ROOT.resolve()) or receipt.exists():raise ValueError("NEW_PRIVATE_RECEIPT_REQUIRED")
        result=extract(args.archive,args.output);new_text(receipt,evidence_json(result));print("PRIVATE_EXTRACTION_COMPLETE")
    except (OSError,ValueError,zipfile.BadZipFile):
        print("EXTRACTION_FAILED_PARTIAL_OUTPUT_PRESERVED_FOR_REVIEW",file=sys.stderr);raise SystemExit(1)
