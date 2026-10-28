import {
  landingDemo as demo,
  microWaveformProfiles,
} from "../fixtures/landingDemo";

export function DemoWaveform({
  focus = false,
  tiny = false,
}: {
  focus?: boolean;
  tiny?: boolean;
}) {
  const left =
    ((demo.targetInterval.startSeconds - demo.detailWindow.startSeconds) /
      (demo.detailWindow.endSeconds - demo.detailWindow.startSeconds)) *
    1000;
  const right =
    ((demo.targetInterval.endSeconds - demo.detailWindow.startSeconds) /
      (demo.detailWindow.endSeconds - demo.detailWindow.startSeconds)) *
    1000;
  const samples = tiny ? microWaveformProfiles[0] : demo.waveform;
  return (
    <svg
      className={`demo-waveform ${focus ? "focused-waveform" : ""}`}
      viewBox="0 0 1000 80"
      preserveAspectRatio="none"
      role="img"
      aria-label={
        focus ? "合成波形示意，蓝色标记单个连续目标音区间" : "合成声音波形示意"
      }
    >
      {focus && (
        <rect
          x={left}
          y="0"
          width={right - left}
          height="80"
          rx="10"
          fill="#dce9ff"
        />
      )}
      <line
        x1="0"
        y1="40"
        x2="1000"
        y2="40"
        stroke="currentColor"
        strokeOpacity=".25"
        strokeDasharray="2 3"
      />
      {samples.map((v, i) => {
        const x = ((i + 0.5) / samples.length) * 1000;
        return (
          <line
            key={i}
            x1={x}
            x2={x}
            y1={40 - v * 35}
            y2={40 + v * 35}
            stroke={focus && (x < left || x > right) ? "#becce4" : "#3876ff"}
            strokeWidth={tiny ? 9 : 2}
            strokeLinecap="round"
          />
        );
      })}
    </svg>
  );
}

export function SpeechCrossSection() {
  return (
    <figure
      className="product-visual cross-section"
      aria-label="发音结构静态演示"
    >
      <div className="structure-row">
        <span className="row-label">Sentence</span>
        <div className="sentence-cell" lang="ja">
          {demo.sentence}
        </div>
      </div>
      <div className="structure-row">
        <span className="row-label">Waveform</span>
        <DemoWaveform />
      </div>
      <div className="structure-row">
        <span className="row-label">Word</span>
        <div className="word-cells" lang="ja">
          {demo.words.map((word, i) => (
            <span key={word} className={i === 1 ? "target-cell" : ""}>
              {word}
            </span>
          ))}
        </div>
      </div>
      <div className="structure-row">
        <span className="row-label">Mora</span>
        <div className="equal-cells" lang="ja">
          {demo.mora.map((m, i) => (
            <span key={m} className={i === 1 ? "target-cell" : ""}>
              {m}
            </span>
          ))}
        </div>
      </div>
      <div className="structure-row">
        <span className="row-label">Phone</span>
        <div className="equal-cells phone-cells">
          {demo.phones.map((p, i) => (
            <span key={p} className={i === 1 ? "target-cell" : ""}>
              {p}
            </span>
          ))}
        </div>
      </div>
      <figcaption>静态演示 · 音素为简化焦点示意</figcaption>
    </figure>
  );
}

export function Distribution({ compact = false }: { compact?: boolean }) {
  const position = (seconds: number) => ((seconds - 0.5) / 2.75) * 100;
  return (
    <div
      className={`distribution ${compact ? "distribution-compact" : ""}`}
      role="img"
      aria-label="合成参考分布示意：你的语音 1.68 秒，参考中位数 2.04 秒；仅静态演示数据"
    >
      {!compact && (
        <div className="distribution-labels">
          <div
            className="distribution-label learner-label"
            style={{ left: `${position(demo.durationSeconds)}%` }}
          >
            你的语音<strong>1.68 s</strong>
          </div>
          <div
            className="distribution-label median-label"
            style={{ left: `${position(demo.referenceMedianSeconds)}%` }}
          >
            中位数<strong>2.04 s</strong>
          </div>
        </div>
      )}
      <div className="histogram">
        {demo.distribution.map((v, i) => (
          <i key={i} style={{ height: `${v * 100}%` }} />
        ))}
        <span
          className="distribution-marker learner-marker"
          style={{ left: `${position(demo.durationSeconds)}%` }}
        />
        <span
          className="distribution-marker median-marker"
          style={{ left: `${position(demo.referenceMedianSeconds)}%` }}
        />
      </div>
      {!compact && (
        <div className="distribution-axis">
          <span>0.5</span>
          <span>1.0</span>
          <span>1.5</span>
          <span>2.0</span>
          <span>2.5</span>
          <span>3.0</span>
          <span>时长 (s)</span>
        </div>
      )}
    </div>
  );
}

export function NativeReferenceVisual() {
  return (
    <figure
      className="product-visual reference-visual"
      aria-label="母语者参考设计的合成视觉演示"
    >
      <div className="reference-header">
        <strong>REFERENCE SET</strong>
        <span>100 independent JVS speakers</span>
      </div>
      <svg
        className="speaker-population"
        viewBox="0 0 600 180"
        role="img"
        aria-label="100 个独立声音的视觉单元，非实际语音测量"
      >
        {Array.from({ length: 100 }, (_, i) => {
          const x = 30 + (i % 10) * 60;
          const y = 9 + Math.floor(i / 10) * 18;
          const profile =
            microWaveformProfiles[
              (i * 5 + Math.floor(i / 10)) % microWaveformProfiles.length
            ];
          const amplitude = 5.5 + (i % 5) * 0.35;
          return (
            <g
              key={i}
              className="micro-waveform-unit"
              opacity={0.5 + (i % 5) * 0.055}
            >
              <line
                x1={x - 24}
                x2={x + 24}
                y1={y}
                y2={y}
                stroke="#d4e2ff"
                strokeWidth=".7"
              />
              {profile.map((value, sample) => (
                <line
                  key={sample}
                  x1={x - 23 + (sample * 46) / (profile.length - 1)}
                  x2={x - 23 + (sample * 46) / (profile.length - 1)}
                  y1={y - value * amplitude}
                  y2={y + value * amplitude}
                  stroke="#487ae4"
                  strokeWidth="1.35"
                  strokeLinecap="round"
                />
              ))}
            </g>
          );
        })}
      </svg>
      <Distribution />
      <figcaption id="reference-design">
        静态设计示意 · 非当前分析结果；参考准入与语境等价性尚未验证。
      </figcaption>
    </figure>
  );
}

export function EvidenceFocusVisual() {
  return (
    <figure
      className="product-visual evidence-visual"
      aria-label="目标音的静态证据演示"
    >
      <div className="target-header">
        <span>目标音</span>
        <b lang="ja">マー</b>
        <b className="phone-pill">/aː/</b>
      </div>
      <div className="target-wave">
        <DemoWaveform focus />
        <div className="wave-time-axis">
          {demo.timelineTicks.map((seconds) => (
            <span
              key={seconds}
              style={{
                left: `${((seconds - demo.detailWindow.startSeconds) / (demo.detailWindow.endSeconds - demo.detailWindow.startSeconds)) * 100}%`,
              }}
            >
              {seconds.toFixed(1)}
            </span>
          ))}
          <span className="axis-unit">时长 (s)</span>
        </div>
      </div>
      <div className="evidence-blocks">
        <div className="evidence-block">
          <h3>时长对比</h3>
          <div className="duration-values">
            <span>
              你的语音<strong>1.68 s</strong>
            </span>
            <span>
              参考中位数<strong>2.04 s</strong>
            </span>
          </div>
          <div className="duration-track">
            <i />
          </div>
          <p className="duration-note">低于母语者参考中位数</p>
        </div>
        <div className="evidence-block">
          <h3>实现形式</h3>
          <div className="realization-target">
            <b lang="ja">マー</b>
            <b>/aː/</b>
          </div>
          <p>完整长音候选实现</p>
        </div>
        <div className="evidence-block">
          <h3>参考分布位置</h3>
          <Distribution compact />
          <p>低于母语者参考中位数</p>
        </div>
      </div>
      <figcaption>Landing 演示数据 · 非实时分析结果</figcaption>
    </figure>
  );
}
