#!/usr/bin/env python3
"""
Script pour nettoyer tous les outputs des notebooks Jupyter avant commit.
Usage: python clear_notebooks.py
"""

import json
import glob
import os
import sys
from pathlib import Path

def clear_notebook_outputs(notebook_path):
    """Clear all outputs from a Jupyter notebook."""
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        
        # Clear outputs and execution counts
        for cell in notebook.get('cells', []):
            if cell.get('cell_type') == 'code':
                cell['outputs'] = []
                cell['execution_count'] = None
                # Clear metadata execution info if present
                if 'metadata' in cell and 'execution' in cell['metadata']:
                    cell['metadata']['execution'] = {}
        
        # Clear notebook metadata execution info
        if 'metadata' in notebook:
            if 'kernelspec' in notebook['metadata']:
                # Keep kernelspec but clear execution-related metadata
                pass
            if 'language_info' in notebook['metadata']:
                # Keep language_info but clear version-specific details that change
                if 'version' in notebook['metadata']['language_info']:
                    del notebook['metadata']['language_info']['version']
        
        # Write back the cleaned notebook
        with open(notebook_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)
        
        print(f"✅ Cleared: {notebook_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error with {notebook_path}: {e}")
        return False

def find_notebooks(root_dir="."):
    """Find all .ipynb files in the project, excluding checkpoints."""
    notebooks = []
    for notebook_path in Path(root_dir).rglob("*.ipynb"):
        # Skip checkpoint files
        if ".ipynb_checkpoints" not in str(notebook_path):
            notebooks.append(str(notebook_path))
    return notebooks

def main():
    """Main function to clear notebook outputs."""
    print("🧹 Nettoyage des outputs des notebooks Jupyter...")

    # If file paths are provided, only process those notebooks.
    args = sys.argv[1:]
    if args:
        notebooks = [
            str(Path(path)) for path in args
            if path.endswith(".ipynb") and Path(path).exists()
        ]
    else:
        notebooks = find_notebooks()
    
    if not notebooks:
        print("Aucun notebook trouvé.")
        return 0
    
    print(f"Trouvé {len(notebooks)} notebook(s)")
    
    success_count = 0
    for notebook in notebooks:
        if clear_notebook_outputs(notebook):
            success_count += 1
    
    print(f"\n🎉 Nettoyage terminé: {success_count}/{len(notebooks)} notebooks traités avec succès")
    
    if success_count == len(notebooks):
        return 0  # Success
    else:
        return 1  # Some errors occurred

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
