#version 140
uniform sampler2DArray p3d_Texture0;
in vec2 vUV;
out vec4 p3d_FragColor;

void main() {
    p3d_FragColor = texture(p3d_Texture0, vec3(vUV, 0.0));
}
