import os
import subprocess
import venv

BUNDLE = globals()["BUNDLE"]
WORK = globals()["WORK"]
DATA = BUNDLE / "data"
RUNTIME_PYTHON = WORK / "runtime" / "bin" / "python"
if not RUNTIME_PYTHON.is_file():
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(WORK / "runtime")
environment = dict(os.environ)
environment["PYTHONNOUSERSITE"] = "1"
for name in ("PYTHONPATH", "PYTHONHOME"):
    environment.pop(name, None)
configuration = (WORK / "runtime" / "pyvenv.cfg").read_text().lower().splitlines()
if "include-system-site-packages = false" not in [line.strip() for line in configuration]:
    raise RuntimeError("The recovery runtime must not inherit global packages.")
subprocess.run(
    [str(RUNTIME_PYTHON), "-I", "-c", "import sys; assert sys.prefix != sys.base_prefix"],
    env=environment, check=True,
)
wheels = list((BUNDLE / "wheels").glob("*.whl"))
if len(wheels) != 1:
    raise RuntimeError("Expected exactly one VERA wheel.")
pip = [str(RUNTIME_PYTHON), "-I", "-m", "pip", "--isolated", "--require-virtualenv"]
subprocess.run(
    pip + ["install", "--quiet", "-r", str(BUNDLE / "requirements-kaggle.txt"), str(wheels[0])],
    env=environment, check=True,
)
subprocess.run(pip + ["check"], env=environment, check=True)

GPU_COUNT = 1
MAX_LENGTH = 2048
RUN_FULL_TRAINING = False
RUN_FINAL_TEST = False
EXPORT_FORMAT = None
RESUME_CHECKPOINT = None
SMOKE = WORK / "smoke-1gpu"
FULL = WORK / "full-1gpu"
SMOKE_REPORT = SMOKE / "report.json"
COMMON = ["--data", DATA, "--max-length", MAX_LENGTH]


def run(module, arguments, distributed=False):
    if GPU_COUNT != 1:
        raise RuntimeError("Keep GPU_COUNT=1 for this recovery smoke run.")
    command_environment = dict(environment)
    command_environment["CUDA_VISIBLE_DEVICES"] = "0"
    subprocess.run(
        [str(RUNTIME_PYTHON), "-I", "-m", module, *[str(item) for item in arguments]],
        env=command_environment, check=True,
    )


print("Isolated runtime ready. Skip the old configuration cell and continue with preflight.")
