#version 140
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 vUV;

void main() {
    vUV = p3d_MultiTexCoord0;
    gl_Position = vec4(p3d_Vertex.x, p3d_Vertex.y + p3d_Vertex.z, 0.0, 1.0);
}
