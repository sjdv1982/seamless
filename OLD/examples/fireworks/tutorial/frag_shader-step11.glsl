#version 130

precision highp float;
uniform vec4 u_color;
uniform highp sampler2D s_texture;

void main()
{
    highp vec4 texColor;
    texColor = texture2D(s_texture, gl_PointCoord);
    gl_FragColor = u_color * texColor;
}
