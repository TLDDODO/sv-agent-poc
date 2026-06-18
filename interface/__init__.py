"""Interface-prediction comparison layer for the FAT10 / MAD2 project.

Several interface-prediction tools each propose which FAT10 residues contact
MAD2. The agents interpret each tool, then adjudicate them into a consensus
interface (residues the tools agree on) versus disputed residues that need MD /
experimental confirmation. This feeds the team's "compare tools -> pick one
interface model for MD" step. The agents never predict the interface
themselves; they compare and audit.
"""
