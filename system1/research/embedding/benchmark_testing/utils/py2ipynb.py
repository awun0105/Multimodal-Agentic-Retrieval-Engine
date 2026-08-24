import sys
import json
import os

def convert(py_file, ipynb_file):
    if not os.path.exists(py_file):
        print(f"Error: File {py_file} not found.")
        return

    with open(py_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    cells = []
    current_cell_type = 'code'
    current_cell_lines = []

    def flush_cell():
        nonlocal current_cell_lines
        if not current_cell_lines:
            return
        # Remove trailing empty lines
        while current_cell_lines and current_cell_lines[-1].strip() == '':
            current_cell_lines.pop()
            
        if current_cell_type == 'markdown':
            # Clean up "# " from markdown lines
            cleaned = []
            for line in current_cell_lines:
                if line.startswith('# '):
                    cleaned.append(line[2:])
                elif line.strip() == '#':
                    cleaned.append('\n')
                else:
                    cleaned.append(line)
            cells.append({
                "cell_type": "markdown",
                "metadata": {},
                "source": cleaned
            })
        else:
            cells.append({
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": current_cell_lines
            })
        current_cell_lines = []

    for line in lines:
        if line.startswith('# %%'):
            flush_cell()
            if '[markdown]' in line:
                current_cell_type = 'markdown'
            else:
                current_cell_type = 'code'
        else:
            current_cell_lines.append(line)

    flush_cell()

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "codemirror_mode": {
                    "name": "ipython",
                    "version": 3
                },
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.10.12"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }

    with open(ipynb_file, 'w', encoding='utf-8') as f:
        json.dump(notebook, f, ensure_ascii=False, indent=2)
    
    print(f"Successfully converted {py_file} to {ipynb_file}")

if __name__ == '__main__':
    if len(sys.argv) == 3:
        py_input = sys.argv[1]
        ipynb_output = sys.argv[2]
    else:
        py_input = "colab_benchmark.py"
        ipynb_output = "embedding_colab_benchmark.ipynb"
    convert(py_input, ipynb_output)
