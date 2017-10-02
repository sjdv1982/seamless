#version 130

attribute vec3 value;

void main () {
  if (u_time <= a_lifetime)
  {
      gl_Position.xyz = a_startPosition + (u_time * a_endPosition);
      gl_Position.xyz += u_centerPosition;
      gl_Position.y -= u_gravity * u_time * u_time;
      gl_Position.w = 1.0;
  }
  else
      gl_Position = vec4(-1000, -1000, 0, 0);

  v_lifetime = 1.0 - (u_time / a_lifetime);
  v_lifetime = clamp(v_lifetime, 0.0, 1.0);
  gl_PointSize = u_pointsize;

  if (u_shrink_with_age)
      gl_PointSize *= (v_lifetime * v_lifetime);
}
