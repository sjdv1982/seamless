#version 130

uniform float u_time;
uniform vec3 u_centerPosition;
uniform float u_pointsize;
uniform float u_gravity;

attribute vec3 value;

void main () {
  gl_Position.xy = u_centerPosition.xy + (u_time + 1) * value.xy;
  gl_Position.y -= u_gravity * u_time * u_time;
  gl_Position.z = 0.0;
  gl_Position.w = 1.0;
  gl_PointSize = u_pointsize;
}
