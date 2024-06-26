//from http://www.mathematik.uni-marburg.de/~thormae/lectures/graphics1/code/WebGLShaderLightMat/ShaderLightMat.html
varying vec3 normalInterp;
varying vec3 vertPos;
varying vec3 color;

const vec3 lightPos = vec3(2.0, 2.0, 1.0);
const vec3 specColor = vec3(1.0, 1.0, 1.0);

void main() {
  vec3 normal = normalize(normalInterp);
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

  gl_FragColor = vec4(lambertian*color + specular*specColor, 1.0);

}
