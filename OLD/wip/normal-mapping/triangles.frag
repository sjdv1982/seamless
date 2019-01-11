#version 130

//from http://www.mathematik.uni-marburg.de/~thormae/lectures/graphics1/code/WebGLShaderLightMat/ShaderLightMat.html
varying vec3 normalInterp;
varying vec3 vertPos;
varying vec3 tangent;
varying vec3 bitangent;
varying vec2 uv;
uniform highp sampler2D s_texture;
uniform highp sampler2D s_normal_map;

const vec3 lightPos = vec3(2.0, 2.0, 1.0);
const vec3 diffuseColor = vec3(1.0, 1.0, 1.0);
const vec3 specColor = vec3(1.0, 1.0, 1.0);

void main() {
  vec3 normal0 = normalInterp;
  vec3 normal_displacement = (texture2D(s_normal_map, uv).xyz -0.5) * 2;
  normal0 *= normal_displacement.z;
  normal0 += normal_displacement.x * tangent;
  normal0 += normal_displacement.y * bitangent;
  vec3 normal = normalize(normal0);
  vec3 lightDir = normalize(lightPos - vertPos);
  vec3 reflectDir = reflect(-lightDir, normal);
  vec3 viewDir = normalize(-vertPos);

  float lambertian = max(dot(lightDir,normal), 0.0);
  float specular = 0.0;

  if(lambertian > 0.0) {

    vec3 viewDir = normalize(-vertPos);
    vec3 halfDir = normalize(lightDir + viewDir);
    float specAngle = max(dot(halfDir, normal), 0.0);
    specular = pow(specAngle, 16.0);

  }

  /*
  vec3 diffuseColor;
  diffuseColor.r = uv.s;
  diffuseColor.g = 0.0;
  diffuseColor.b = uv.t;
  */
  vec4 frag_color = vec4(lambertian*diffuseColor + specular*specColor, 1.0);
  vec4 tex_color = texture2D(s_texture, uv);
  //tex_color = vec4(1.0,1.0,1.0,1.0);

  gl_FragColor = frag_color * tex_color;

}
