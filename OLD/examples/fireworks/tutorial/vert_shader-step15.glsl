#version 130

uniform float u_time;
uniform vec3 u_centerPosition;
uniform float u_pointsize;
uniform float u_gravity;
uniform bool u_shrink_with_age;
attribute float a_lifetime;
attribute vec3 a_startPosition;
attribute vec3 a_endPosition;
varying float v_lifetime;

void main () {
  if (u_time <= a_lifetime)
  {
      gl_Position.xyz = a_startPosition + (u_time * a_endPosition);
      gl_Position.xyz += u_centerPosition;
      gl_Position.y -= u_gravity * u_time * u_time;
      gl_Position.z = 0.0;
      gl_Position.w = 1.0;
  }
  else
      gl_Position = vec4(-1000, -1000, 0, 0);

  v_lifetime = 1.0 - (u_time / a_lifetime);
  v_lifetime = clamp(v_lifetime, 0.0, 1.0);
  gl_PointSize = u_pointsize;

  float f;
  if (u_shrink_with_age) {
      f = v_lifetime;
      gl_PointSize = u_pointsize * f;
  }
}
