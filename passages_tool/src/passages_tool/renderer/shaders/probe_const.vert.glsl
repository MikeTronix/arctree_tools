#version 120
attribute vec4 p3d_Vertex;

void main() {
    // CardMaker frame (±1, ±1) lives in XY or XZ depending on Panda version.
    // Map those axes straight to NDC so camera pose cannot hide the probe.
    gl_Position = vec4(p3d_Vertex.x, p3d_Vertex.y + p3d_Vertex.z, 0.0, 1.0);
}
