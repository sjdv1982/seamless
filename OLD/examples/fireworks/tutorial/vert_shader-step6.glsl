#version 130

attribute vec3 value;
uniform float u_time;

void main () {
  gl_Position.xy = (u_time + 1) * value.xy;
  gl_Position.z = 0.0;
  gl_Position.w = 1.0;
  gl_PointSize = 10;
}
