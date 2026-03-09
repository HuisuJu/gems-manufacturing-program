"""
Minimal wrapper package for selected Matter CHIP Python utilities.

This package exposes:
- SPAKE2+ verifier generation
- Setup payload generation (QR / manual code)
"""

from .spake2p import generate_verifier
from .SetupPayload import SetupPayload, CommissioningFlow