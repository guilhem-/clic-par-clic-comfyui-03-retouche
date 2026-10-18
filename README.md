# Retoucher une image — un second workflow ComfyUI pour Open WebUI

Démonstration du module 3 de la série « Clic par clic » **Générer des images dans Open WebUI avec
ComfyUI** : le serveur d'images de l'organisation sait générer ; il apprend à **retoucher**. Un
second workflow ComfyUI, avec un modèle spécialisé dans la retouche (FLUX.2 [klein] 4B, Apache
2.0), est branché dans la section « Modification d'image » d'Open WebUI ; l'utilisateur dépose une
photo dans la conversation et décrit ce qu'il veut changer.

Vidéo : {{video}}

## But

- Dans ComfyUI, le workflow « Serveur d'images — retouche » : chargement de l'image (nœud 76),
  consigne (74), chargeur du modèle de retouche (70), et une **taille lue sur l'image d'origine**
  (99) transmise par des liens à l'image vide (66) et au planificateur (62) : le résultat garde les
  proportions de la photo. Exporté au format API (`workflows/retouche.json`).
- Dans Open WebUI, la section « Modification d'image » : moteur ComfyUI, adresse du serveur (la
  retouche ne reprend pas celle de la génération), workflow, correspondance `image` / 76,
  **`text`** / 74 (et non `prompt`), `unet_name` / 70, largeur et hauteur vides, modèle de
  retouche.
- Dans la conversation, l'outil intégré `edit_image` : la photo déposée est retouchée, puis
  l'image déjà retouchée.

| Fichier | Contenu |
|---|---|
| `workflows/retouche.json` | Workflow de retouche au format API, **tel qu'exporté dans la vidéo** |
| `workflows/retouche.interface.json` | Le même graphe au format de l'interface de ComfyUI (19 nœuds, numéros d'origine du modèle Comfy-Org « FLUX.2 Klein 4B distilled image edit », premier sous-graphe décompressé) |
| `images/tasse.png` | La photo de la démonstration (1216 × 832), générée par le serveur d'images du module 1 |
| `open-webui/reglages-retouche.md` | Tous les champs de la section, la correspondance, ce que fait Open WebUI à chaque retouche |
| `activer_retouche.py` | La section réglée par l'API d'Open WebUI, contrôle de la correspondance, essai, retour arrière |

## Prérequis

- Le serveur d'images des modules 1 et 2 : ComfyUI v0.41 sur une carte graphique, branché dans
  Open WebUI 0.11 (page Images) —
  [`clic-par-clic-comfyui-01-brancher`](https://github.com/guilhem-/clic-par-clic-comfyui-01-brancher),
  [`clic-par-clic-comfyui-02-workflow-organisation`](https://github.com/guilhem-/clic-par-clic-comfyui-02-workflow-organisation).
- Dans `models/` de ComfyUI : `diffusion_models/flux-2-klein-4b-fp8.safetensors`
  ([black-forest-labs/FLUX.2-klein-4b-fp8](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8)),
  `vae/flux2-vae.safetensors`, et l'encodeur de texte déjà utilisé pour la génération,
  `text_encoders/qwen_3_4b_fp8_mixed.safetensors` (le modèle Comfy-Org attend la version bf16 de
  8 Go : la version fp8 suffit). Aucun nœud personnalisé.
- Une carte de 8 Go suffit : ComfyUI charge le modèle de retouche à la place de celui de
  génération (environ 25 s de bascule, puis une quinzaine de secondes par retouche).
- Un compte **administrateur** d'Open WebUI ; pour les utilisateurs : la permission « Génération
  d'image » et un modèle de conversation qui a cette capacité (et sait appeler des outils).

## Installation pas à pas

### 1. Le workflow, dans ComfyUI

1. Déposez `images/tasse.png` dans le dossier `input/` de ComfyUI (ou chargez-la dans le nœud
   « Charger Image ») et ouvrez `workflows/retouche.interface.json` (glisser-déposer dans
   l'interface) — ou `python activer_retouche.py --comfyui`.
2. Repérez les numéros (Paramètres › « Mode de badge d'identifiant de nœud » › « Afficher tout ») :
   76 chargement, 74 consigne, 70 chargeur, 99 lecture de la taille.
3. Menu **Fichier › Exporter (API)**, nom `retouche`.

### 2. La section « Modification d'image », dans Open WebUI, à la main comme dans la vidéo

Panneau d'administration › Réglages › Images, en bas : activer **Modification d'image** ;
moteur **ComfyUI** ; Base URL `http://comfyui.comfyui.svc.cluster.local:8188` (vérifier) ;
« Workflow ComfyUI » › **Téléverser** `retouche.json` ; correspondance : Image* `image` / `76`,
Prompt* **`text`** / `74`, Model `unet_name` / `70`, Width et Height vides ; Modèle
`flux-2-klein-4b-fp8.safetensors` ; taille vide ; **Enregistrer**. Détail :
`open-webui/reglages-retouche.md`.

### 2 bis. Par l'API

```bash
cp .env.example .env                     # OWUI_URL, OWUI_JETON (administrateur), COMFYUI_URL…
python activer_retouche.py --verifier    # contrôle du workflow et de la correspondance
python activer_retouche.py               # sauvegarde la configuration en place (images-avant.json), branche la retouche
python activer_retouche.py --essai       # retouche d'essai de images/tasse.png par Open WebUI
python activer_retouche.py --couper      # désactive la modification d'image
python activer_retouche.py --retablir    # revient à la configuration sauvegardée
```

La page Images est un réglage **de toute l'instance** : `images-avant.json` garde la configuration
précédente, clés comprises (fichier ignoré par git, ne le partagez pas).

## Essai

Avec un compte utilisateur : nouvelle conversation, menu « Intégrations » › « Image », déposez
`images/tasse.png`, puis « Pose cette tasse sur un bureau en bois clair, avec la lumière du matin.
Garde le logo. » Dépliez l'appel `edit_image` : la consigne rédigée par le modèle de conversation
et l'identifiant de l'image jointe. Enchaînez : « Maintenant, la même scène en hiver, avec de la
neige dehors, derrière la fenêtre. » — le modèle retouche l'image qu'il vient de produire.

## Bon à savoir

- **Consignes ciblées ou scènes entières** : une consigne ciblée (« change la couleur du logo en
  bleu nuit ») ne touche que ce qui est demandé. Une consigne qui change la scène peut parfois
  modifier l'objet lui-même (anse, logo) : « Garde le logo » aide ; vérifiez le résultat.
- **Ni étapes ni graine** pour la retouche dans Open WebUI : elles sont fixées dans le workflow.
- **Deux images à combiner** : deux nœuds de chargement, et deux numéros sur la ligne « Image* »
  (une image par numéro, dans l'ordre).
- **Deux modèles pour une carte** : ComfyUI charge l'un, puis l'autre ; la première retouche après
  une génération attend le chargement du modèle de retouche. Mesures et file d'attente : module 7.
- **Nettoyage** : les images envoyées par Open WebUI restent dans `input/` de ComfyUI (noms
  `<uuid>.png`), les résultats dans `output/openwebui/` (préfixe `openwebui/retouche`) ; Open WebUI
  garde sa propre copie de chaque image.

## Série

- Module précédent : **Le workflow de l'organisation** —
  [`clic-par-clic-comfyui-02-workflow-organisation`](https://github.com/guilhem-/clic-par-clic-comfyui-02-workflow-organisation).
- Module suivant : **Un outil qui choisit le format** (outil Open WebUI « Atelier d'images ») —
  `clic-par-clic-comfyui-04-…` (à paraître).

## Licence

MIT (voir `LICENSE`). ComfyUI : GPL-3.0 ; FLUX.2 [klein] 4B et l'encodeur Qwen3 : Apache 2.0 ;
Open WebUI : sa propre licence (le code cité dans la vidéo reste le sien, il n'est pas recopié ici).
