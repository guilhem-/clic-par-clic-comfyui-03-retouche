"""Connect image editing (the "Image Edit" section) in Open WebUI, through its API.

Does what module 3 of the "Image generation in Open WebUI with ComfyUI" series does on screen,
in Admin Panel > Settings > Images, "Image Edit" section:
  1. turns image editing on, ComfyUI engine;
  2. fills in the image server address (editing does not reuse the one of generation);
  3. uploads the editing workflow in API format (workflows/image-editing.json);
  4. sets the node mapping: image -> node 76 (loading), text -> node 74 (instruction),
     unet_name -> node 70 (loader); width and height empty (the size follows the original image);
  5. sets the editing model; the editing size stays empty.
Generation (module 2) is not touched.

Before saving, the script checks that each row targets a value of the workflow, and never a
link: Open WebUI would write the value over the link, without a message.

Usage:
  python setup_editing.py               # back up the current configuration (images-config.backup.json), connect editing
  python setup_editing.py --check       # check the workflow and the node mapping, without changing anything
  python setup_editing.py --test IMG    # test edit of a local image through Open WebUI (address of the file produced)
  python setup_editing.py --disable     # turn image editing off (the rest of the section is kept)
  python setup_editing.py --restore     # put back the configuration saved in images-config.backup.json
  python setup_editing.py --comfyui     # drop the workflow (interface format) and the sample photo into ComfyUI

The backup images-config.backup.json holds the whole configuration of the Images page, keys
included: it is ignored by git, do not share it.

Settings: .env file (see .env.example); environment variables take precedence.
No dependency: Python 3.10 or newer, standard library only.
"""
import base64
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = pathlib.Path(__file__).resolve().parent
BACKUP = HERE / "images-config.backup.json"
WORKFLOW = HERE / "workflows" / "image-editing.json"
VARIABLES = ("OWUI_URL", "OWUI_TOKEN", "COMFYUI_URL", "COMFYUI_INTERFACE", "EDIT_MODEL")

# Node mapping of image editing: (Open WebUI row, key, node number; None: row left empty).
NODE_MAPPING = [
    ("image", "image", "76"),      # LoadImage: Open WebUI writes the name of the file sent to ComfyUI
    ("prompt", "text", "74"),      # CLIPTextEncode: the instruction (the suggested key, "prompt", is wrong here)
    ("model", "unet_name", "70"),  # UNETLoader: the editing model
    ("width", "width", None),      # empty: the size is read on the original image (node 99)
    ("height", "height", None),
]


def settings() -> dict:
    """Defaults (those of the video), then .env (key=value), then the environment, which wins."""
    s = {
        "OWUI_URL": "http://127.0.0.1:8080",
        "COMFYUI_URL": "http://comfyui.comfyui.svc.cluster.local:8188",
        "COMFYUI_INTERFACE": "http://comfyui.localhost:8080",
        "EDIT_MODEL": "flux-2-klein-4b-fp8.safetensors",
    }
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                s[key.strip()] = value.strip()
    for key in VARIABLES:
        if os.environ.get(key):
            s[key] = os.environ[key]
    return s


S = settings()


def request(method: str, url: str, body=None, headers=None, raw: bytes | None = None, content_type="application/json"):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": content_type, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            text = resp.read().decode()
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url}: {e.code} {e.read().decode()[:300]}")
    return json.loads(text) if text.strip().startswith(("{", "[")) else text


def api(method: str, path: str, body=None):
    """Call Open WebUI's API with an administrator token."""
    if not S.get("OWUI_TOKEN"):
        sys.exit("OWUI_TOKEN missing (.env): token of an Open WebUI administrator account.")
    return request(method, S["OWUI_URL"].rstrip("/") + path, body, {"Authorization": f"Bearer {S['OWUI_TOKEN']}"})


def read_workflow() -> tuple[str, dict]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return text, json.loads(text)


def check(workflow: dict) -> list[str]:
    """Problems of the node mapping: missing node, missing key, or a key that holds a link."""
    problems = []
    for type_, key, node in NODE_MAPPING:
        if node is None:
            continue
        if node not in workflow:
            problems.append(f"{type_}: node {node} does not exist in the workflow")
            continue
        inputs = workflow[node].get("inputs", {})
        if key not in inputs:
            problems.append(f"{type_}: node {node} ({workflow[node].get('class_type')}) has no key {key}")
        elif isinstance(inputs[key], list):
            problems.append(f"{type_}: {node}.{key} is a link to node {inputs[key][0]}: the value would overwrite it")
    # The size follows the original image: empty image and scheduler linked to the size reading.
    for node in ("66", "62"):
        width = workflow.get(node, {}).get("inputs", {}).get("width")
        if not isinstance(width, list):
            problems.append(f"node {node} has a fixed width ({width}): the edit would not keep the proportions")
    return problems


def setup() -> None:
    text, workflow = read_workflow()
    problems = check(workflow)
    if problems:
        sys.exit("Node mapping refused:\n  " + "\n  ".join(problems))
    config = api("GET", "/api/v1/images/config")
    if not BACKUP.exists():
        BACKUP.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Current configuration saved to {BACKUP.name} (python setup_editing.py --restore)")
    config.update({
        "ENABLE_IMAGE_EDIT": True,
        "IMAGE_EDIT_ENGINE": "comfyui",
        "IMAGE_EDIT_MODEL": S.get("EDIT_MODEL", "flux-2-klein-4b-fp8.safetensors"),
        "IMAGE_EDIT_SIZE": "",
        # Exactly the origin that serves the images, without a trailing slash (Open WebUI's anti-SSRF check).
        "IMAGES_EDIT_COMFYUI_BASE_URL": S.get("COMFYUI_URL", "").rstrip("/"),
        "IMAGES_EDIT_COMFYUI_API_KEY": "",
        "IMAGES_EDIT_COMFYUI_WORKFLOW": text,
        "IMAGES_EDIT_COMFYUI_WORKFLOW_NODES": [{"type": t, "key": k, "node_ids": [n] if n else []} for t, k, n in NODE_MAPPING],
    })
    api("POST", "/api/v1/images/config/update", config)
    print("Image editing connected: image -> 76, text -> 74, unet_name -> 70, width and height empty.")
    if not config.get("ENABLE_IMAGE_GENERATION"):
        print("Warning: image generation is off; the edit_image tool is only offered when it is on.")


def disable() -> None:
    config = api("GET", "/api/v1/images/config")
    config["ENABLE_IMAGE_EDIT"] = False
    api("POST", "/api/v1/images/config/update", config)
    print("Image editing turned off.")


def check_workflow() -> None:
    _, workflow = read_workflow()
    problems = check(workflow)
    print("Editing workflow: " + ("node mapping correct" if not problems else "; ".join(problems)))


def test(image: str) -> None:
    data = base64.b64encode(pathlib.Path(image).read_bytes()).decode()
    images = api("POST", "/api/v1/images/edit", {
        "prompt": "Change the color of the logo to midnight blue.",
        "image": f"data:image/png;base64,{data}",
    })
    for img in images or []:
        print(f"Edited image: {S['OWUI_URL'].rstrip('/')}{img['url']}")


def restore() -> None:
    if not BACKUP.exists():
        sys.exit(f"{BACKUP.name} not found: nothing to restore.")
    api("POST", "/api/v1/images/config/update", json.loads(BACKUP.read_text(encoding="utf-8")))
    BACKUP.unlink()
    print("Images configuration restored.")


def comfyui() -> None:
    """Drop the sample photo (input folder) and the workflow (interface format) into ComfyUI."""
    base = S.get("COMFYUI_INTERFACE", "").rstrip("/")
    if not base:
        sys.exit("COMFYUI_INTERFACE missing (.env): address of ComfyUI's interface in the browser.")
    # ComfyUI refuses a request whose Origin header does not match its address.
    origin = {"Origin": base}
    boundary = uuid.uuid4().hex
    photo = (HERE / "images" / "mug.png").read_bytes()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"mug.png\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + photo + (
            f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ninput"
            f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n").encode()
    request("POST", f"{base}/api/upload/image", raw=body, headers=origin, content_type=f"multipart/form-data; boundary={boundary}")
    name = urllib.parse.quote("workflows/Image server — image editing.json", safe="")
    request("POST", f"{base}/api/userdata/{name}?overwrite=true", raw=(HERE / "workflows" / "image-editing.interface.json").read_bytes(), headers=origin)
    print('Photo "mug.png" and workflow "Image server — image editing" dropped into ComfyUI.')


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console: dashes and quotes readable
    if "--restore" in sys.argv:
        restore()
    elif "--check" in sys.argv:
        check_workflow()
    elif "--test" in sys.argv:
        i = sys.argv.index("--test")
        test(sys.argv[i + 1] if len(sys.argv) > i + 1 else str(HERE / "images" / "mug.png"))
    elif "--disable" in sys.argv:
        disable()
    elif "--comfyui" in sys.argv:
        comfyui()
    else:
        setup()
