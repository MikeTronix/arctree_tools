#version 120
uniform sampler2D p3d_Texture0;
uniform sampler2D heightTex;
uniform float uHeightScale;
uniform vec2 uSizeMeters;
varying vec2 vUV;
varying vec3 vViewTS;

void main() {
    vec3 vd = vViewTS;
    float vz = vd.z;
    vec2 uv = vUV;
    if (uHeightScale > 1e-4 && vz >= 0.12) {
        vec2 uvPerM = vec2(
            1.0 / max(uSizeMeters.x, 0.001),
            1.0 / max(uSizeMeters.y, 0.001)
        );
        vec2 dir = (vd.xy / vz) * uvPerM * uHeightScale;
        const int STEPS = 12;
        float stepH = 1.0 / float(STEPS);
        vec2 dUV = -dir * stepH;
        float rayH = 1.0;
        float hitH = texture2D(heightTex, uv).r;
        for (int i = 0; i < STEPS; i++) {
            if (rayH <= hitH + 0.001) {
                break;
            }
            uv += dUV;
            rayH -= stepH;
            if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
                discard;
            }
            hitH = texture2D(heightTex, uv).r;
        }
    }
    vec3 col = texture2D(p3d_Texture0, uv).rgb;
    float ndotv = clamp(vz / max(length(vd), 1e-4), 0.28, 1.0);
    gl_FragColor = vec4(col * ndotv, 1.0);
}
