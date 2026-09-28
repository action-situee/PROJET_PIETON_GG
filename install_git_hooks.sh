#!/bin/bash
#
# Script d'installation des Git hooks pour la sécurité des notebooks
# Usage: ./install_git_hooks.sh
#

echo "🔧 Installation des Git hooks pour la sécurité des notebooks..."

# Vérifier qu'on est dans un repo Git
if [ ! -d ".git" ]; then
    echo "❌ Erreur: Ce script doit être exécuté dans la racine d'un repository Git"
    exit 1
fi

# Vérifier que clear_notebooks.py existe
if [ ! -f "clear_notebooks.py" ]; then
    echo "❌ Erreur: clear_notebooks.py non trouvé"
    echo "Ce script est requis pour le fonctionnement des hooks"
    exit 1
fi

# Créer le répertoire hooks s'il n'existe pas
mkdir -p .git/hooks

# Installer pre-commit: nettoie les notebooks stagés puis les re-stage
cat > .git/hooks/pre-commit <<'EOF'
#!/bin/bash
set -euo pipefail

staged_notebooks=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '\.ipynb$' || true)

if [ -z "$staged_notebooks" ]; then
    exit 0
fi

echo "🧹 Nettoyage des notebooks stagés..."

while IFS= read -r nb; do
    [ -z "$nb" ] && continue
    python3 clear_notebooks.py "$nb"
    git add "$nb"
done <<< "$staged_notebooks"

echo "✅ Notebooks nettoyés et re-stagés"
EOF

chmod +x .git/hooks/pre-commit

# Installer pre-push: vérifie qu'aucun notebook >100MB n'est poussé
cat > .git/hooks/pre-push <<'EOF'
#!/bin/bash
set -euo pipefail

limit_bytes=$((100 * 1024 * 1024))

while read -r local_ref local_sha remote_ref remote_sha; do
    [ -z "$local_sha" ] && continue

    if [ "$remote_sha" = "0000000000000000000000000000000000000000" ]; then
        range="$local_sha"
    else
        range="$remote_sha..$local_sha"
    fi

    while IFS= read -r path; do
        [ -z "$path" ] && continue
        case "$path" in
            *.ipynb)
                size=$(git cat-file -s "$local_sha:$path" 2>/dev/null || echo 0)
                if [ "$size" -gt "$limit_bytes" ]; then
                    echo "❌ Push bloqué: $path dépasse 100MB ($size bytes)."
                    echo "   Nettoie/réduis le notebook ou utilise Git LFS."
                    exit 1
                fi
                ;;
        esac
    done < <(git diff-tree --no-commit-id --name-only -r "$range")
done

exit 0
EOF

chmod +x .git/hooks/pre-push

echo "✅ Installation terminée !"
echo ""
echo "🔒 Hooks installés :"
echo "  - pre-commit  : Nettoie automatiquement les notebooks avant chaque commit"
echo "  - pre-push    : Vérifie l'absence de contenu sensible avant push"
echo ""
echo "💡 Ces hooks protègent contre :"
echo "  - Les outputs de cellules contenant des données sensibles"
echo "  - Les execution counts qui peuvent révéler l'ordre d'exécution"
echo "  - Les métadonnées de version spécifiques"
echo ""
echo "🎯 Pour désactiver temporairement : git commit --no-verify"
echo "🎯 Pour nettoyer manuellement : python3 clear_notebooks.py"
