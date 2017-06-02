#version 130

precision highp float;
uniform sampler2D texture1;
varying vec3 v_color;
varying float v_lifetime;
uniform highp sampler2D s_texture;

void main()
{
    highp vec4 texColor;
    texColor = texture2D(s_texture, gl_PointCoord);
    gl_FragColor = vec4(v_color,1.0) * texColor;
    //gl_FragColor.a *= v_lifetime;
}
