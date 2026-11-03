import os
import shutil
import sys

Import("env")

local = os.path.join(env["PROJECT_DIR"], "ccache.exe")
executable = local if sys.platform.startswith("win32") and os.path.isfile(local) else shutil.which("ccache")
if executable:
    cache_dir = os.path.join(env["PROJECT_DIR"], ".ccache", env.get("PIOENV", "default"))
    os.makedirs(cache_dir, exist_ok=True)
    cache_env = {
        "CCACHE_DIR": cache_dir,
        "CCACHE_SLOPPINESS": "pch_defines,time_macros,include_file_mtime,include_file_ctime,file_macro,locale",
        "CCACHE_COMPRESS": "1", "CCACHE_COMPRESSLEVEL": "6", "CCACHE_MAXSIZE": "200M",
        "CCACHE_BASEDIR": env["PROJECT_DIR"]
    }
    os.environ.update(cache_env)
    env.Append(ENV=dict(os.environ))
    for variable in ("CCCOM", "CXXCOM", "ASCOM"):
        if variable in env:
            env[variable] = f'"{executable}" {env[variable]}'
    print(f"[ccache] Enabled: {executable}")
else:
    print("[ccache] Not installed; compiling without a compiler cache.")
