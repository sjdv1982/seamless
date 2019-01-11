uniform mat4 u_mvp_matrix;
uniform mat4 u_modelview_matrix;
uniform mat3 u_normal_matrix;
attribute vec3  a_position;
attribute vec3  a_normal;
attribute vec3  a_tangent;
attribute vec3  a_bitangent;
attribute vec2  a_uv;

varying vec3 normalInterp;
varying vec3 tangent;
varying vec3 bitangent;
varying vec3 vertPos;
varying vec3 texcolor;
varying vec2 uv;

//adapted from http://www.mathematik.uni-marburg.de/~thormae/lectures/graphics1/code/WebGLShaderLightMat/ShaderLightMat.html
void main() {
  gl_Position = u_mvp_matrix * vec4(a_position, 1.0);

  // all following gemetric computations are performed in the
  // camera coordinate system (aka eye coordinates)
  vec3 normal = u_normal_matrix * a_normal;
  gl_Position = u_mvp_matrix * vec4(a_position, 1.0);
  vec4 vertPos4 = u_modelview_matrix * vec4(a_position, 1.0);
  vertPos = vec3(vertPos4) / vertPos4.w;
  normalInterp = u_normal_matrix * a_normal;
  tangent = u_normal_matrix * a_tangent;
  bitangent = u_normal_matrix * a_bitangent;
  uv = a_uv;
}
