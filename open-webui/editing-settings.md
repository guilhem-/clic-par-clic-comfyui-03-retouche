# "Image Edit" section of Open WebUI 0.11 — settings of module 3

Admin Panel › Settings › Images, at the bottom of the page. Editing has **its own fields**: it
reuses neither the address, nor the key, nor the workflow of generation.

| Field | Value | Configuration key |
|---|---|---|
| Image Edit (switch) | on | `ENABLE_IMAGE_EDIT` |
| Image Edit Engine | ComfyUI | `IMAGE_EDIT_ENGINE` = `comfyui` |
| Model | `flux-2-klein-4b-fp8.safetensors` (file name seen in the loader, node 70) | `IMAGE_EDIT_MODEL` |
| Image Size | **empty** | `IMAGE_EDIT_SIZE` |
| Base URL | `http://comfyui.comfyui.svc.cluster.local:8188` (no trailing slash); verify icon: "Server connection verified" | `IMAGES_EDIT_COMFYUI_BASE_URL` |
| API Key | empty (ComfyUI has no authentication) | `IMAGES_EDIT_COMFYUI_API_KEY` |
| ComfyUI Workflow | `workflows/image-editing.json` (API format) | `IMAGES_EDIT_COMFYUI_WORKFLOW` |
| ComfyUI Workflow Nodes | see below | `IMAGES_EDIT_COMFYUI_WORKFLOW_NODES` |

The "Model" field is required: empty, Open WebUI would write an empty string into the loader and
ComfyUI would refuse the request.

## Node mapping

| Row | Key | Node Ids | Workflow node |
|---|---|---|---|
| Image* | `image` (suggested) | `76` | `LoadImage`: Open WebUI writes the name under which ComfyUI stored the uploaded image |
| Prompt* | **`text`** (the suggested key, `prompt`, matches no input of this node) | `74` | `CLIPTextEncode`: the instruction |
| Model | `unet_name` (suggested) | `70` | `UNETLoader` |
| Width | `width` | **empty** | — |
| Height | `height` | **empty** | — |

Width and height empty: the size is read on the original image (node 99, `GetImageSize`, after the
scaling to one megapixel of node 80) and passed through links to the empty image (66) and to the
scheduler (62). The result keeps the proportions of the photo (1216 × 832 → 1232 × 832 in the
video). A size set here would be passed to Open WebUI, but without a node number it would be
written nowhere.

**Neither steps nor seed**: the node mapping of editing has no such rows. They stay set in the
workflow: 4 steps (node 62), seed 0 (node 73, `RandomNoise`). The same image and the same
instruction therefore give the same edit.

## What Open WebUI does for each edit

Code: [`backend/open_webui/routers/images.py`](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/routers/images.py),
function `image_edits`, branch `IMAGE_EDIT_ENGINE == 'comfyui'`:

1. each image (address of a file of the chat, read then converted) is sent to ComfyUI by
   `comfyui_upload_image` (`POST /api/upload/image`, `input/` folder) under a random name
   (`<uuid>.png`); ComfyUI returns the name it kept;
2. the request holds the list of these names, the instruction, and a width and height only if a
   size is set;
3. the workflow is filled in as for a generation (`_apply_workflow_nodes` of
   `utils/images/comfyui.py`): the `image` row writes **one image per number, in order** — two
   load nodes and two numbers make it possible to combine two images;
4. ComfyUI computes; Open WebUI fetches the image produced and stores it among its files.

On the chat side, the built-in tool `edit_image` (parameters `prompt` and `image_urls`) is only
offered to the model if generation **and** editing are on, the user has the "Image Generation"
permission, the model has this capability, and the user turned on "Image" in the Integrations
menu. The model receives the list of attached files (`<attached_files>`) and chooses the image to
edit: the dropped photo, or the image it has just produced.
