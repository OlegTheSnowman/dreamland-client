import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dlclient.version import VERSION  # noqa: E402

NAME = "DreamLand"


def main():
    dist = os.path.join(HERE, "dist")
    sep = os.pathsep
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", NAME,
        "--distpath", dist, "--workpath", os.path.join(HERE, "build"), "--specpath", os.path.join(HERE, "build"),
        "--add-data", os.path.join(HERE, "sounds") + sep + "sounds",
        "--add-data", os.path.join(HERE, "dlclient", "defaults.js") + sep + "dlclient",
        "--collect-all", "accessible_output2",
        "--collect-all", "quickjs",
        "--collect-submodules", "pygame",
        os.path.join(HERE, "dreamland.pyw"),
    ]
    subprocess.check_call(args)
    folder = os.path.join(dist, NAME)
    for extra in ("LICENSE", "README.md"):
        shutil.copy(os.path.join(HERE, extra), folder)
    archive = os.path.join(dist, "%s-%s-windows.zip" % (NAME, VERSION))
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(folder):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.join(NAME, os.path.relpath(full, folder)))
    print(archive)


if __name__ == "__main__":
    main()
