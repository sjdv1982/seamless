Example demonstrating the use of seamless in 3D rendering.

The example will be demonstrated in a video tutorial on
https://www.youtube.com/playlist?list=PL6WSTyQSLz08_GQqj-NyshaWnoIZMsqTK .
This video tutorial is planned for August - September 2017.


Scripts
=======

test-sphere.py
**************
This shows the generation of a sphere from parameters.
The main purpose is to demonstrate that seamless can give you live feedback
during algorithm development (video in progress).
The sphere-generating algorithm itself is of secondary importance.

test-ply.py
***********
Loads a PLY file. Depends on Python library "plyfile")
In the 3D window, press key 1-4 to change the states:
1. wireframe
2. flat-shaded triangles
3. flat-shaded triangles + wireframe
4. smooth-shaded triangles

This example uses the following external resources:

triangles.frag: Phong-Blinn shader adapted from
http://www.mathematik.uni-marburg.de/~thormae/lectures/graphics1/code/WebGLShaderLightMat/ShaderLightMat.html

suzanne.ply: mascot model from Blender (www.blender.org)

lion-statue.ply: created by Jason Shoumar, downloaded from https://clara.io/view/bb15ed37-2155-4964-98e0-f330b2e0a6ef#, public domain

Metallic Lucy (Stanford scan): created by Ben Houston, downloaded from https://clara.io/view/454f1f28-0f63-4664-aeef-cf7aecd9cd40#, public domain

test-atom.py
************
Uses the sphere generation to visualize simple Protein Data Bank (PDB) files.
