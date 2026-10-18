"""Brancher la retouche d'image (section « Modification d'image ») dans Open WebUI, par son API.

Fait ce que le module 3 de la série « Générer des images dans Open WebUI avec ComfyUI » fait à
l'écran, dans Panneau d'administration › Réglages › Images, section « Modification d'image » :
  1. active la modification d'image, moteur ComfyUI ;
  2. renseigne l'adresse du serveur d'images (la retouche ne reprend pas celle de la génération) ;
  3. téléverse le workflow de retouche au format API (workflows/retouche.json) ;
  4. pose la correspondance : image → nœud 76 (chargement), text → nœud 74 (consigne),
     unet_name → nœud 70 (chargeur) ; largeur et hauteur vides (la taille suit l'image d'origine) ;
  5. indique le modèle de retouche ; la taille de la retouche reste vide.
La génération (module 2) n'est pas touchée.

Avant d'enregistrer, le script vérifie que chaque ligne vise une valeur du workflow, et jamais un
lien : Open WebUI écrirait la valeur par-dessus le lien, sans message.

Usage :
  python activer_retouche.py               # sauvegarde la configuration en place (images-avant.json), branche la retouche
  python activer_retouche.py --verifier    # contrôle le workflow et la correspondance, sans rien changer
  python activer_retouche.py --essai IMG   # retouche d'essai d'une image locale par Open WebUI (adresse du fichier produit)
  python activer_retouche.py --couper      # désactive la modification d'image (le reste de la section est gardé)
  python activer_retouche.py --retablir    # remet la configuration sauvegardée dans images-avant.json
  python activer_retouche.py --comfyui     # dépose le workflow (format de l'interface) et la photo d'exemple dans ComfyUI

La sauvegarde images-avant.json contient la configuration complète de la page Images, clés
comprises : elle est ignorée par git, ne la partagez pas.

Réglages : fichier .env (voir .env.example) ; les variables d'environnement l'emportent.
Aucune dépendance : Python 3.10 ou plus récent, bibliothèque standard seulement.
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

ICI = pathlib.Path(__file__).resolve().parent
SAUVEGARDE = ICI / "images-avant.json"
WORKFLOW = ICI / "workflows" / "retouche.json"
VARIABLES = ("OWUI_URL", "OWUI_JETON", "COMFYUI_URL", "COMFYUI_INTERFACE", "MODELE_RETOUCHE")

# Correspondance de la retouche : (ligne d'Open WebUI, clé, numéro du nœud ; None : ligne laissée vide).
CORRESPONDANCE = [
    ("image", "image", "76"),      # LoadImage : Open WebUI y écrit le nom du fichier envoyé à ComfyUI
    ("prompt", "text", "74"),      # CLIPTextEncode : la consigne (la clé proposée, « prompt », est fausse ici)
    ("model", "unet_name", "70"),  # UNETLoader : le modèle de retouche
    ("width", "width", None),      # vide : la taille est lue sur l'image d'origine (nœud 99)
    ("height", "height", None),
]


def reglages() -> dict:
    """Valeurs par défaut (celles de la vidéo), puis .env (clé=valeur), puis l'environnement, qui l'emporte."""
    r = {
        "OWUI_URL": "http://127.0.0.1:8080",
        "COMFYUI_URL": "http://comfyui.comfyui.svc.cluster.local:8188",
        "COMFYUI_INTERFACE": "http://comfyui.localhost:8080",
        "MODELE_RETOUCHE": "flux-2-klein-4b-fp8.safetensors",
    }
    env = ICI / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, valeur = ligne.split("=", 1)
                r[cle.strip()] = valeur.strip()
    for cle in VARIABLES:
        if os.environ.get(cle):
            r[cle] = os.environ[cle]
    return r


R = reglages()


def requete(methode: str, url: str, corps=None, entetes=None, brut: bytes | None = None, type_contenu="application/json"):
    donnees = brut if brut is not None else (None if corps is None else json.dumps(corps).encode())
    req = urllib.request.Request(url, data=donnees, method=methode, headers={"Content-Type": type_contenu, **(entetes or {})})
    try:
        with urllib.request.urlopen(req, timeout=600) as rep:
            texte = rep.read().decode()
    except urllib.error.HTTPError as e:
        sys.exit(f"{methode} {url} : {e.code} {e.read().decode()[:300]}")
    return json.loads(texte) if texte.strip().startswith(("{", "[")) else texte


def api(methode: str, chemin: str, corps=None):
    """Appel de l'API d'Open WebUI avec le jeton d'un administrateur."""
    if not R.get("OWUI_JETON"):
        sys.exit("OWUI_JETON manquant (.env) : jeton d'un compte administrateur d'Open WebUI.")
    return requete(methode, R["OWUI_URL"].rstrip("/") + chemin, corps, {"Authorization": f"Bearer {R['OWUI_JETON']}"})


def lire_workflow() -> tuple[str, dict]:
    texte = WORKFLOW.read_text(encoding="utf-8")
    return texte, json.loads(texte)


def verifier(workflow: dict) -> list[str]:
    """Problèmes de la correspondance : nœud absent, clé absente, ou clé qui porte un lien."""
    problemes = []
    for type_, cle, noeud in CORRESPONDANCE:
        if noeud is None:
            continue
        if noeud not in workflow:
            problemes.append(f"{type_} : le nœud {noeud} n'existe pas dans le workflow")
            continue
        entrees = workflow[noeud].get("inputs", {})
        if cle not in entrees:
            problemes.append(f"{type_} : le nœud {noeud} ({workflow[noeud].get('class_type')}) n'a pas de clé {cle}")
        elif isinstance(entrees[cle], list):
            problemes.append(f"{type_} : {noeud}.{cle} est un lien vers le nœud {entrees[cle][0]} : la valeur l'écraserait")
    # La taille suit l'image d'origine : image vide et planificateur reliés à la lecture de la taille.
    for noeud in ("66", "62"):
        largeur = workflow.get(noeud, {}).get("inputs", {}).get("width")
        if not isinstance(largeur, list):
            problemes.append(f"le nœud {noeud} a une largeur fixe ({largeur}) : la retouche ne garderait pas les proportions")
    return problemes


def activer() -> None:
    texte, workflow = lire_workflow()
    problemes = verifier(workflow)
    if problemes:
        sys.exit("Correspondance refusée :\n  " + "\n  ".join(problemes))
    config = api("GET", "/api/v1/images/config")
    if not SAUVEGARDE.exists():
        SAUVEGARDE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Configuration en place sauvegardée dans {SAUVEGARDE.name} (python activer_retouche.py --retablir)")
    config.update({
        "ENABLE_IMAGE_EDIT": True,
        "IMAGE_EDIT_ENGINE": "comfyui",
        "IMAGE_EDIT_MODEL": R.get("MODELE_RETOUCHE", "flux-2-klein-4b-fp8.safetensors"),
        "IMAGE_EDIT_SIZE": "",
        # Exactement l'origine qui sert les images, sans barre finale (contrôle anti-SSRF d'Open WebUI).
        "IMAGES_EDIT_COMFYUI_BASE_URL": R.get("COMFYUI_URL", "").rstrip("/"),
        "IMAGES_EDIT_COMFYUI_API_KEY": "",
        "IMAGES_EDIT_COMFYUI_WORKFLOW": texte,
        "IMAGES_EDIT_COMFYUI_WORKFLOW_NODES": [{"type": t, "key": k, "node_ids": [n] if n else []} for t, k, n in CORRESPONDANCE],
    })
    api("POST", "/api/v1/images/config/update", config)
    print("Retouche branchée : image → 76, text → 74, unet_name → 70, largeur et hauteur vides.")
    if not config.get("ENABLE_IMAGE_GENERATION"):
        print("Attention : la génération d'image est coupée ; l'outil edit_image n'est proposé que si elle est active.")


def couper() -> None:
    config = api("GET", "/api/v1/images/config")
    config["ENABLE_IMAGE_EDIT"] = False
    api("POST", "/api/v1/images/config/update", config)
    print("Modification d'image désactivée.")


def controler() -> None:
    _, workflow = lire_workflow()
    problemes = verifier(workflow)
    print("Workflow de retouche : " + ("correspondance juste" if not problemes else "; ".join(problemes)))


def essai(image: str) -> None:
    donnees = base64.b64encode(pathlib.Path(image).read_bytes()).decode()
    images = api("POST", "/api/v1/images/edit", {
        "prompt": "Change the color of the logo to midnight blue.",
        "image": f"data:image/png;base64,{donnees}",
    })
    for img in images or []:
        print(f"Image retouchée : {R['OWUI_URL'].rstrip('/')}{img['url']}")


def retablir() -> None:
    if not SAUVEGARDE.exists():
        sys.exit(f"{SAUVEGARDE.name} introuvable : rien à rétablir.")
    api("POST", "/api/v1/images/config/update", json.loads(SAUVEGARDE.read_text(encoding="utf-8")))
    SAUVEGARDE.unlink()
    print("Configuration Images rétablie.")


def comfyui() -> None:
    """Dépose la photo d'exemple (dossier d'entrée) et le workflow (format de l'interface) dans ComfyUI."""
    base = R.get("COMFYUI_INTERFACE", "").rstrip("/")
    if not base:
        sys.exit("COMFYUI_INTERFACE manquant (.env) : adresse de l'interface de ComfyUI dans le navigateur.")
    # ComfyUI refuse une requête dont l'en-tête Origin ne correspond pas à son adresse.
    origine = {"Origin": base}
    limite = uuid.uuid4().hex
    photo = (ICI / "images" / "tasse.png").read_bytes()
    corps = (f"--{limite}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"tasse.png\"\r\n"
             f"Content-Type: image/png\r\n\r\n").encode() + photo + (
             f"\r\n--{limite}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ninput"
             f"\r\n--{limite}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{limite}--\r\n").encode()
    requete("POST", f"{base}/api/upload/image", brut=corps, entetes=origine, type_contenu=f"multipart/form-data; boundary={limite}")
    nom = urllib.parse.quote("workflows/Serveur d'images — retouche.json", safe="")
    requete("POST", f"{base}/api/userdata/{nom}?overwrite=true", brut=(ICI / "workflows" / "retouche.interface.json").read_bytes(), entetes=origine)
    print("Photo « tasse.png » et workflow « Serveur d'images — retouche » déposés dans ComfyUI.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows : accents lisibles
    if "--retablir" in sys.argv:
        retablir()
    elif "--verifier" in sys.argv:
        controler()
    elif "--essai" in sys.argv:
        i = sys.argv.index("--essai")
        essai(sys.argv[i + 1] if len(sys.argv) > i + 1 else str(ICI / "images" / "tasse.png"))
    elif "--couper" in sys.argv:
        couper()
    elif "--comfyui" in sys.argv:
        comfyui()
    else:
        activer()
