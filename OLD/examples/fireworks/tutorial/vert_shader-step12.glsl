#version 130

uniform float u_time;
uniform vec3 u_centerPosition;
uniform float u_pointsize;
uniform float u_gravity;

attribute vec3 a_startPosition;
attribute vec3 a_endPosition;

void main () {
  gl_Position.xyz = a_startPosition + (u_time * a_endPosition);
  gl_Position.xyz += u_centerPosition;
  gl_Position.y -= u_gravity * u_time * u_time;
  gl_Position.z = 0.0;
  gl_Position.w = 1.0;
  gl_PointSize = u_pointsize;
}
