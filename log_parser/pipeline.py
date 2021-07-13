import subprocess as subp
from pathlib import Path
import sys
import argparse
import shutil

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline for downloading and processing into parameters for trading strategy")
    parser.add_argument("pathtologs", help="If set, grabs sandbox data instead of production data")
    parser.add_argument("-sandbox", action="store_true", help="If set, grabs sandbox data instead of production data")
    args = parser.parse_args()

    dot = Path()

    if args.sandbox:
        print("Sandbox")
        top_dir = "pipeline_sandbox"
        storj_folder = "logs"
    else:
        print("Production")
        top_dir = "pipeline"
        storj_folder = "production_logs"

    if not (dot/top_dir).exists():
        (dot/top_dir).mkdir()

    # 1) Get log archives from Storj
    # try:
    #     subp.run(["go", "run", "get_logs.go", top_dir, storj_folder], check=True)
    # except subp.CalledProcessError:
    #     print("Error downloading logs, try again ...")
    #     sys.exit(1)

    # 1) Move log archives into pipeline
    out0 = dot/top_dir/"0"
    if not out0.exists():
        out0.mkdir()

    for a in Path(args.pathtologs).rglob("*.tar.gz"):
        shutil.move(a, out0/a.name)
        

    # 2) Process log archives into csvs
    subp.run(["python", "process_archives.py", dot/top_dir/"0", dot/top_dir/"1"])

    # 3) Process csvs into pkls and generate graphs
    subp.run(["python", "process_csvs.py", dot/top_dir/"1", dot/top_dir/"2"])

    # 4) Run parameter search in simulations over training data
    subp.run(["python", "optimize.py", dot/top_dir/"2", dot/top_dir/"3"])

