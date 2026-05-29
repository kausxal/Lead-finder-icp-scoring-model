import os
import sys
import subprocess
import importlib
import site

os.chdir(os.path.dirname(os.path.abspath(__file__)))

py_ver = f"{sys.version_info.major}{sys.version_info.minor}"

# Add site-packages for current Python version
site_pkgs = []
try:
    site_pkgs = site.getsitepackages()
except Exception:
    pass
try:
    user_site = site.getusersitepackages()
    if user_site and os.path.isdir(user_site) and user_site not in site_pkgs:
        site_pkgs.append(user_site)
except Exception:
    pass

for root in [
    os.path.join(os.path.expanduser(r"~\AppData\Roaming\Python"), f"Python{py_ver}", "site-packages"),
    os.path.join(os.path.expanduser(r"~\AppData\Local\Programs\Python"), f"Python{py_ver}", "Lib", "site-packages"),
    f"C:\\Python{py_ver}\\Lib\\site-packages",
]:
    if os.path.isdir(root) and root not in site_pkgs:
        site_pkgs.append(root)

for p in site_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

REQUIRED = ["customtkinter", "pandas", "requests", "openpyxl"]

def try_import_all():
    missing = []
    for pkg in REQUIRED:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    return missing

missing = try_import_all()

if missing:
    print(f"Python {sys.version_info.major}.{sys.version_info.minor} missing: {', '.join(missing)}")
    print(f"Executable: {sys.executable}")
    print("\nTrying to install...")

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + missing,
        capture_output=True, text=True, timeout=120,
    )
    print(result.stdout[-200:].strip())
    if result.returncode != 0:
        print(result.stderr[-200:].strip())

    importlib.invalidate_caches()
    for p in site_pkgs:
        if p not in sys.path:
            sys.path.insert(0, p)
    importlib.invalidate_caches()

    still_missing = try_import_all()

    if still_missing:
        print(f"\nStill missing: {', '.join(still_missing)}")
        print("The current Python environment has broken/corrupted packages.")
        print("\nSearching for a working Python installation...")

        # Find other Python installs and test if they work
        candidates = []
        base_user = os.path.expanduser(r"~\AppData\Local\Programs\Python")
        for ver_dir in os.listdir(base_user) if os.path.isdir(base_user) else []:
            exe = os.path.join(base_user, ver_dir, "python.exe")
            if os.path.exists(exe) and exe != sys.executable:
                candidates.append(exe)
        for root in ["C:\\Python314", "C:\\Python313", "C:\\Python312"]:
            exe = os.path.join(root, "python.exe")
            if os.path.exists(exe) and exe != sys.executable and exe not in candidates:
                candidates.append(exe)

        found = None
        for exe in candidates:
            try:
                r = subprocess.run(
                    [exe, "-c", "; ".join(f"import {p}" for p in REQUIRED) + "; print('ok')"],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode == 0 and r.stdout.strip() == "ok":
                    found = exe
                    print(f"  Found working Python: {exe}")
                    break
            except:
                pass

        if found:
            print(f"\nLaunching with {found}...")
            subprocess.call([found] + sys.argv)
            sys.exit(0)

        print(f"\nCould not find or install packages.")
        print(f"Run this in a terminal:\n  pip install {' '.join(REQUIRED)}")
        input("\nPress Enter to exit...")
        sys.exit(1)
    else:
        print("All packages resolved.")

try:
    from gui import TerrascopeApp
    app = TerrascopeApp()
    app.mainloop()
except Exception as e:
    import traceback
    with open("crash_log.txt", "w") as f:
        f.write(traceback.format_exc())
    print(f"FATAL: {e}")
    input("\nPress Enter to exit...")
    sys.exit(1)
