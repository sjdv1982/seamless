#version 130

precision highp float;
uniform highp sampler2D s_texture;

void main()
{
    highp vec4 texColor;
    texColor = texture2D(s_texture, gl_PointCoord);
    gl_FragColor = vec4(1.0, 1.0, 1.0, 0.2) * texColor;
}
