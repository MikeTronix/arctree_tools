#version 120
attribute vec4 p3d_Vertex;
attribute vec3 p3d_Normal;
attribute vec2 p3d_MultiTexCoord0;
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat3 p3d_NormalMatrix;
varying vec2 vUV;
varying vec3 vViewTS;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    vUV = p3d_MultiTexCoord0;
    vec3 nV = normalize(p3d_NormalMatrix * p3d_Normal);
    vec3 upV = normalize(p3d_ModelViewMatrix[2].xyz);
    vec3 tV = cross(upV, nV);
    if (dot(tV, tV) < 1e-6) {
        tV = cross(vec3(0.0, 1.0, 0.0), nV);
    }
    tV = normalize(tV);
    vec3 bV = normalize(cross(nV, tV));
    vec4 posV = p3d_ModelViewMatrix * p3d_Vertex;
    vec3 viewV = -posV.xyz;
    vViewTS = vec3(dot(viewV, tV), dot(viewV, bV), dot(viewV, nV));
}
