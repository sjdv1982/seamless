uniform mat4 u_mvp_matrix;
uniform mat4 u_modelview_matrix;
uniform mat3 u_normal_matrix;
attribute float a_radius;
attribute vec3 a_position;
attribute vec3 a_coordinate;
attribute vec3 a_normal;
attribute vec3 a_color;
varying vec3 normalInterp;
varying vec3 vertPos;
varying vec3 color;

//adapted from http://www.mathematik.uni-marburg.de/~thormae/lectures/graphics1/code/WebGLShaderLightMat/ShaderLightMat.html
void main() {
  vec3 p = a_radius * a_coordinate + a_position;
  gl_Position = u_mvp_matrix * vec4(p, 1.0);

  // all following gemetric computations are performed in the
  // camera coordinate system (aka eye coordinates)
  vec3 normal = u_normal_matrix * a_normal;
  vec4 vertPos4 = u_modelview_matrix * vec4(p, 1.0);
  vertPos = vec3(vertPos4) / vertPos4.w;
  normalInterp = u_normal_matrix * a_normal;
  color = a_color;

}
