"""Verify the two built APKs without installing or accessing a device."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess


def output(*command):
    return subprocess.check_output(command, text=True)


def manifest_nodes(tree):
    nodes, stack = [], []
    for line in tree.splitlines():
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if stripped.startswith("E: "):
            while stack and stack[-1][0] >= indent:
                stack.pop()
            node = {"tag": stripped.split()[1], "attrs": {}}
            nodes.append(node)
            stack.append((indent, node))
        elif stripped.startswith("A: ") and stack:
            match = re.match(r'A: (?:android:)?([^=(]+)(?:\([^)]*\))?=(.*)', stripped)
            if match:
                stack[-1][1]["attrs"][match[1]] = match[2]
    return nodes


def verify(build_tools):
    permissions = []
    for flavor, package, label in (
        ("companion", "com.jarvisos.companion", "JarvisOS Companion"),
        ("understandingLab", "com.jarvisos.companion.understandinglab", "JarvisOS Understanding Lab"),
    ):
        apk = Path(f"companion/android/app/build/outputs/apk/{flavor}/debug/app-{flavor}-debug.apk")
        badging = output(str(build_tools / "aapt"), "dump", "badging", str(apk))
        assert f"package: name='{package}'" in badging, badging
        assert f"application-label:'{label}'" in badging, badging
        nodes = manifest_nodes(output(str(build_tools / "aapt"), "dump", "xmltree", str(apk), "AndroidManifest.xml"))
        # Dependency providers must use the flavor application ID as authority.
        for node in nodes:
            if node["tag"] == "provider":
                authority = node["attrs"].get("authorities", "")
                quoted = re.search(r'"([^"]+)"', authority)
                assert quoted and all(a.startswith(package + ".") for a in quoted[1].split(";")), authority
            if node["tag"] == "action" and "START_LOCAL_AI" in node["attrs"].get("name", ""):
                assert f'"{package}.action.START_LOCAL_AI"' in node["attrs"]["name"]
            if node["tag"] in ("service", "receiver"):
                name = node["attrs"].get("name", "")
                if "LocalAIHostService" in name or "LocalAIHostTriggerReceiver" in name:
                    exported = node["attrs"].get("exported", "")
                    assert ("0xffffffff" if flavor == "companion" else "0x0") in exported, node
        permissions.append({name.replace(package, "APPLICATION_ID")
                            for name in re.findall(r"uses-permission: name='([^']+)'", badging)})
        signature = output(str(build_tools / "apksigner"), "verify", "--verbose", "--print-certs", str(apk))
        print(f"{flavor}: package={package}; label={label}")
        print(f"APK SHA-256: {hashlib.sha256(apk.read_bytes()).hexdigest()}")
        print(signature)
    assert permissions[0] == permissions[1], "Lab must not add permissions"
    print("Verified: distinct packages/labels, scoped authorities/actions, Lab private host components, identical permissions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-tools", type=Path, required=True)
    verify(parser.parse_args().build_tools)
