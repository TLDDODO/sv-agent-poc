#!/usr/bin/env python3
"""Render the labeled FAT10-MAD2 hero figure from the MD complex (reproducible).

Input  : complex_protein.pdb  (frame 1 of the MD trajectory, water stripped:
           cpptraj -> trajin .. 1 1 ; strip !(:1-370) ; trajout complex_protein.pdb pdb)
Output : interface.png (PyMOL render) and interface_labeled.png (with on-figure labels)

Needs: pymol-open-source, pillow.   Run:  python -m analysis.render_structure
Colours: grey = MAD2 (166-370); blue = FAT10 UBL1 6-81 (NMR-expected site);
         wheat = FAT10 82-158; red sticks = persistent MD interface (159-165 + 97/135-138).
"""
import os

PDB = "complex_protein.pdb"


def render():
    import pymol
    pymol.finish_launching(['pymol', '-qc'])
    from pymol import cmd
    cmd.load(PDB, 'cplx')
    cmd.hide('everything'); cmd.show('cartoon'); cmd.bg_color('white')
    cmd.color('grey70', 'resi 166-370')               # MAD2
    cmd.color('skyblue', 'resi 1-81')                 # FAT10 UBL1 (NMR-expected site)
    cmd.color('wheat', 'resi 82-158')                 # FAT10 rest
    cmd.color('red', 'resi 159-165+97+135-138')       # persistent MD interface
    cmd.show('sticks', 'resi 159-165+97+135-138 and not hydro')
    cmd.set('stick_radius', '0.3')
    cmd.set('cartoon_transparency', '0.15', 'resi 166-370')
    cmd.set('ray_opaque_background', 0)
    cmd.orient(); cmd.turn('y', 15); cmd.turn('x', -5)
    cmd.ray(1800, 1350)
    cmd.png('interface.png', dpi=300)


def add_labels():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open('interface.png').convert('RGB')
    d = ImageDraw.Draw(img)
    fp = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    big = ImageFont.truetype(fp, 54); small = ImageFont.truetype(fp, 38)

    def label(xy, lines, color, leader=None):
        x, y = xy
        if leader:
            d.line([(x + 10, y + 30), leader], fill=color, width=4)
        for i, (t, f) in enumerate(lines):
            d.text((x, y + i * 52), t, fill=color, font=f)

    label((40, 40), [("FAT10 UBL1", big), ("NMR-expected MAD2 site", small)], (20, 90, 200))
    label((1380, 40), [("MAD2", big)], (70, 70, 70))
    label((600, 1170), [("MD interface", big), ("(C-terminal — actual contact)", small)],
          (200, 20, 20), leader=(1030, 900))
    img.save('interface_labeled.png')


if __name__ == "__main__":
    if not os.path.exists(PDB):
        raise SystemExit(f"missing {PDB} — make it with cpptraj (see module docstring)")
    render()
    add_labels()
    print("WROTE interface.png + interface_labeled.png")
