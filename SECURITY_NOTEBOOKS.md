# Sécurité des notebooks Jupyter

## Vue d'ensemble

Ce dépôt est équipé d'un système de protection contre la publication accidentelle de données sensibles dans les notebooks Jupyter. Le système nettoie automatiquement les outputs, execution counts et métadonnées d'exécution avant chaque commit.

## Protection automatique

### Hooks Git installés

- `pre-commit` : nettoie automatiquement les notebooks stagés avant chaque commit.
- `pre-push` : vérifie qu'aucun notebook trop volumineux n'est poussé.

### Ce qui est automatiquement nettoyé

- outputs de cellules ;
- execution counts ;
- métadonnées d'exécution ;
- informations locales susceptibles de varier selon l'environnement.

## Installation

```bash
git clone https://github.com/action-situee/projet-index-walk-bike-ge-gg.git
cd projet-index-walk-bike-ge-gg

./install_git_hooks.sh
```

## Utilisation quotidienne

```bash
jupyter lab

git add .
git commit -m "Mon commit"
git push
```

## Support

### Problèmes courants

Si un hook ne fonctionne pas :

```bash
chmod +x .git/hooks/pre-commit
chmod +x .git/hooks/pre-push

./install_git_hooks.sh
```

Ce système ne remplace pas un contrôle manuel. Avant de publier, vérifier aussi `git status --short`, `git diff --stat` et l'absence de fichiers issus de `Data/`.
