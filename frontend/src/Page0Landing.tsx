import { Arrow, Plus } from "./components/Icons";
import { VoiceInputActions } from "./components/VoiceInputActions";
import { StaticBlueWave } from "./components/StaticBlueWave";
import { HeroVideoBackground } from "./components/HeroVideoBackground";
import workspacePreview from "./assets/workspace-preview.png";
import demoStructure from "./assets/demo-structure.jpg";
import demoProsody from "./assets/demo-prosody.jpg";
import demoReference from "./assets/demo-reference.jpg";
import demoEvidence from "./assets/demo-evidence.jpg";

function ProductScreenshot({ src, alt, width, height, reference = false }: {
  src: string; alt: string; width: number; height: number; reference?: boolean;
}) {
  return (
    <figure
      className={`product-visual product-screenshot${reference ? " reference-visual" : ""}`}
      id={reference ? "reference-design" : undefined}
      aria-label={alt}
    >
      <img src={src} alt={alt} width={width} height={height} loading="lazy" decoding="async" />
    </figure>
  );
}

function StartLink() {
  return (
    <a
      className="button button-primary"
      href="#/workspace"
    >
      开始使用 <Arrow />
    </a>
  );
}
function Navbar() {
  return (
    <header className="navbar container">
      <a className="brand" href="#top">
        Japanese Speech X-Ray
      </a>
      <nav aria-label="主导航">
        <a href="#story">产品介绍</a>
        <a href="#structure">核心功能</a>
        <a href="#reference">参考数据</a>
        <a href="#footer">使用说明</a>
      </nav>
      <span className="navbar-github">本地体验版</span>
    </header>
  );
}
function VoiceEntry() {
  const enterWorkspace = () => { window.location.hash = "#/workspace"; };
  return (
    <div className="voice-entry-wrap" id="voice-entry" tabIndex={-1}>
      <div className="voice-entry" role="group" aria-label="进入工作区上传或录音">
        <button
          type="button"
          className="upload-button"
          aria-label="进入工作区上传 WAV"
          onClick={enterWorkspace}
        >
          <Plus />
        </button>
        <span className="voice-placeholder">
          <span className="desktop-placeholder">
            说一句日语，开始分析……
          </span>
          <span className="mobile-placeholder">说一句日语，开始分析……</span>
        </span>
        <VoiceInputActions onActivate={enterWorkspace} />
      </div>
      <p className="format-note">支持上传 WAV · Mono PCM16 · 8–48 kHz · 点击进入工作区选句与录音</p>
    </div>
  );
}
function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <HeroVideoBackground />
      <div className="hero-content container">
        <h1 id="hero-title">
          <span>JAPANESE</span> <span>SPEECH</span> <span>X-RAY</span>
        </h1>
        <p className="hero-subtitle">让日语发音变得可见、可比、可检查。</p>
        <div className="hero-actions">
          <StartLink />
          <a className="button button-secondary" href="#/workspace?demo=learner-v1-001">
            产品演示
          </a>
        </div>
        <VoiceEntry />
      </div>
    </section>
  );
}
export function Page0Landing() {
  return (
    <div id="top" className="page0-landing">
      <a className="skip-link" href="#main-content">
        跳至主要内容
      </a>
      <Navbar />
      <main id="main-content" tabIndex={-1}>
        <Hero />
        <figure className="workspace-preview container" aria-label="分析工作台界面预览">
          <img
            src={workspacePreview}
            width={1920}
            height={1080}
            alt="Japanese Speech X-Ray 分析工作台：左侧当前会话与三条 DEMO，中间上传、录音及分析输入框"
            loading="lazy"
            decoding="async"
          />
        </figure>
        <div className="container product-story">
          <section
            className="story-intro"
            id="story"
            aria-labelledby="story-title"
          >
            <h2 id="story-title">听见之外，将发音“可视化”</h2>
          </section>
          <section
            className="story-section structure-section"
            id="structure"
            aria-labelledby="structure-title"
          >
            <div className="section-copy">
              <h2 id="structure-title">
                看见声音里的
                <br />
                发音结构。
              </h2>
              <p>
                从句子、单词到音拍和音素，
                <br className="desktop-break" />
                观察实验性声音结构；也可直接试听和手动练习。
              </p>
            </div>
            <ProductScreenshot
              src={demoStructure}
              alt="DEMO 实际界面截图：スマートフォン的真实波形、词、音拍和模型原生音素结构"
              width={897}
              height={513}
            />
          </section>
          <section
            className="story-section prosody-section image-left-section"
            id="prosody"
            aria-labelledby="prosody-title"
          >
            <div className="section-copy">
              <h2 id="prosody-title">
                看见音高的变化，
                <br />
                感受语调的起伏。
              </h2>
              <p>
                把声音的高低变化绘成曲线，对照同句合成参考，边听边看，找到想练习的片段。
              </p>
            </div>
            <ProductScreenshot
              src={demoProsody}
              alt="DEMO 实际界面截图：音高与语调的真实频率曲线及同句 Haruka 合成参考"
              width={886}
              height={763}
            />
          </section>
          <section
            className="story-section reference-section"
            id="reference"
            aria-labelledby="reference-title"
          >
            <div className="section-copy">
              <h2 id="reference-title">
                母语者参考，
                <br />
                不是一个标准答案。
              </h2>
              <p>
                探索 JVS 母语者材料中的目标词。
                自动边界与参考分布仍在验证，不作为个人发音标准。
              </p>
              <div className="reference-note">
                <div>
                  <p>研究参考设计：100 位独立 JVS 说话者</p>
                  <a href="#reference-design">
                    了解参考设计 <Arrow />
                  </a>
                </div>
              </div>
            </div>
            <ProductScreenshot
              src={demoReference}
              alt="DEMO 实际界面截图：语速归一化参考摘要、中位数及 100 位 JVS 说话者来源说明"
              width={897}
              height={334}
              reference
            />
          </section>
          <section
            className="story-section evidence-section image-left-section"
            id="evidence"
            aria-labelledby="evidence-title"
          >
            <div className="section-copy">
              <h2 id="evidence-title">
                聚焦真正需要看的
                <br />
                那个声音。
              </h2>
              <p>
                试听原音，选择目标区域，查看候选与证据限制。当前不提供发音评分。
              </p>
            </div>
            <ProductScreenshot
              src={demoEvidence}
              alt="DEMO 实际界面截图：目标音候选区间、试听操作、参考位置和证据限制"
              width={897}
              height={519}
            />
          </section>
        </div>
        <section className="closing" aria-labelledby="closing-title">
          <div className="closing-background">
            <StaticBlueWave />
          </div>
          <div className="closing-content container">
            <h2 id="closing-title">从声音，到证据。</h2>
            <p>录制日语、试听关键片段，借助音高与同句参考反复练习。</p>
            <StartLink />
          </div>
        </section>
      </main>
      <footer className="footer container" id="footer">
        <p className="landing-use-note">本地练习：进入工作区选句 → 录音或上传 WAV → 试听与框选 → 查看可用音高 → 对照 Haruka 合成参考 → 再次录音。当前不提供发音正确率。</p>
        <div className="footer-top">
          <a className="brand" href="#top">
            Japanese Speech X-Ray
          </a>
          <a href="#story">About</a>
          <span>© 2026</span>
        </div>
      </footer>
    </div>
  );
}
