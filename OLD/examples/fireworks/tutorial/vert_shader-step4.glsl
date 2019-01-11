#version 130

attribute vec3 value;

void main () {
  gl_Position.xyz = value;
  gl_Position.w = 1.0;
  gl_PointSize = 10;
}
