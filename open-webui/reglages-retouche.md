# Section « Modification d'image » d'Open WebUI 0.11 — réglages du module 3

Panneau d'administration › Réglages › Images, en bas de la page. La retouche a **ses propres
champs** : elle ne reprend ni l'adresse, ni la clé, ni le workflow de la génération.

| Champ (FR) | Valeur | Clé de configuration |
|---|---|---|
| Modification d'image (interrupteur) | activé | `ENABLE_IMAGE_EDIT` |
| Moteur de modification d'image | ComfyUI | `IMAGE_EDIT_ENGINE` = `comfyui` |
| Modèle | `flux-2-klein-4b-fp8.safetensors` (nom du fichier vu dans le chargeur, nœud 70) | `IMAGE_EDIT_MODEL` |
| Taille de l'image | **vide** | `IMAGE_EDIT_SIZE` |
| Base URL | `http://comfyui.comfyui.svc.cluster.local:8188` (sans barre finale) ; icône de vérification : « Connexion au serveur vérifiée » | `IMAGES_EDIT_COMFYUI_BASE_URL` |
| Clé API | vide (ComfyUI n'a pas d'authentification) | `IMAGES_EDIT_COMFYUI_API_KEY` |
| Workflow ComfyUI | `workflows/retouche.json` (format API) | `IMAGES_EDIT_COMFYUI_WORKFLOW` |
| Noeuds du workflow ComfyUI | voir ci-dessous | `IMAGES_EDIT_COMFYUI_WORKFLOW_NODES` |

Le champ « Modèle » est obligatoire : vide, Open WebUI écrirait une chaîne vide dans le chargeur et
ComfyUI refuserait la demande.

## Correspondance

| Ligne | Clé | ID des noeuds | Nœud du workflow |
|---|---|---|---|
| Image* | `image` (proposée) | `76` | `LoadImage` : Open WebUI y écrit le nom sous lequel ComfyUI a rangé l'image envoyée |
| Prompt* | **`text`** (la clé proposée, `prompt`, ne correspond à aucune entrée de ce nœud) | `74` | `CLIPTextEncode` : la consigne |
| Model | `unet_name` (proposée) | `70` | `UNETLoader` |
| Width | `width` | **vide** | — |
| Height | `height` | **vide** | — |

Largeur et hauteur vides : la taille est lue sur l'image d'origine (nœud 99, `GetImageSize`, après
la mise à l'échelle à un mégapixel du nœud 80) et transmise par des liens à l'image vide (66) et au
planificateur (62). Le résultat garde les proportions de la photo (1216 × 832 → 1232 × 832 dans la
vidéo). Une taille fixée ici serait passée à Open WebUI, mais sans numéro de nœud elle ne serait
écrite nulle part.

**Ni étapes ni graine** : la correspondance de la retouche n'a pas ces lignes. Elles restent
fixées dans le workflow : 4 étapes (nœud 62), graine 0 (nœud 73, `RandomNoise`). Même image et même
consigne donnent donc la même retouche.

## Ce que fait Open WebUI à chaque retouche

Code : [`backend/open_webui/routers/images.py`](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/routers/images.py),
fonction `image_edits`, branche `IMAGE_EDIT_ENGINE == 'comfyui'` :

1. chaque image (adresse d'un fichier de la conversation, lue puis convertie) est envoyée à ComfyUI
   par `comfyui_upload_image` (`POST /api/upload/image`, dossier `input/`) sous un nom aléatoire
   (`<uuid>.png`) ; ComfyUI renvoie le nom retenu ;
2. la demande contient la liste de ces noms, la consigne, et une largeur et une hauteur seulement si
   une taille est fixée ;
3. le workflow est rempli comme pour une génération (`_apply_workflow_nodes` de
   `utils/images/comfyui.py`) : la ligne `image` écrit **une image par numéro, dans l'ordre** —
   deux nœuds de chargement et deux numéros permettent de combiner deux images ;
4. ComfyUI calcule ; Open WebUI récupère l'image produite et la range parmi ses fichiers.

Côté conversation, l'outil intégré `edit_image` (paramètres `prompt` et `image_urls`) n'est proposé
au modèle que si la génération **et** la modification d'image sont activées, que l'utilisateur a la
permission « Génération d'image », que le modèle a cette capacité, et que l'utilisateur a activé
« Image » dans le menu des intégrations. Le modèle reçoit la liste des fichiers joints
(`<attached_files>`) et choisit l'image à retoucher : la photo déposée, ou l'image qu'il vient de
produire.
