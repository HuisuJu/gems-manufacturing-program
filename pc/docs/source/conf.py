# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Make pc/src importable (for stream.serial autodoc)
sys.path.insert(0, os.path.abspath('../../src'))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'GEMS Factory PC Program'
copyright = '2026, Alice Ju'
author = 'Alice Ju'
release = '0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
	'sphinx.ext.autodoc',
	'sphinx.ext.autosummary',
	'sphinx.ext.napoleon',
	'sphinx.ext.viewcode',
]

autosummary_generate = True

autodoc_default_options = {
	'members': True,
	'undoc-members': True,
	'show-inheritance': True,
}

napoleon_google_docstring = True
napoleon_numpy_docstring = False

# Optional runtime dependency used by stream.serial
autodoc_mock_imports = ['cobs']

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'

html_theme_options = {
	'navigation_depth': 4,
	'collapse_navigation': False,
	'sticky_navigation': True,
	'style_external_links': True,
}

html_static_path = ['_static']
