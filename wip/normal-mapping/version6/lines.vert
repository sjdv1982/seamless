#version 130

uniform mat4 u_mvp_matrix;
attribute vec3  a_position;
attribute vec3  a_color;
varying float fade_factor;
varying vec3 v_color;

void main() {
  gl_Position = u_mvp_matrix * vec4(a_position, 1.0);
  gl_Position.z -= 0.0001;
  float depth = length(gl_Position);
  fade_factor = smoothstep(25.0, 10.0, depth);
  v_color = a_color;
}
