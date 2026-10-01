import { useState } from "react";
import { ArrowUpRight, Check, CircleHelp, Clock3, MapPin, ShieldCheck, Sparkles, Wrench } from "lucide-react";
import { createServiceRequest } from "./services/api";

const examplePrompts = [
  "The kitchen sink is leaking under the cabinet",
  "My AC is running but not cooling the bedroom",
  "There is a power issue in two rooms",
];

function validateDescription(description: string): string | null {
  const trimmedDescription = description.trim();

  if (!trimmedDescription) {
    return "Tell us what needs fixing before continuing.";
  }

  if (!/\p{L}/u.test(trimmedDescription)) {
    return "Add a few words describing the repair.";
  }

  return null;
}

export default function App() {
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedJobId, setSubmittedJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedDescription = description.trim();
    const validationError = validateDescription(trimmedDescription);

    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      const result = await createServiceRequest({ user_prompt: trimmedDescription });
      setSubmittedJobId(result.job_id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function chooseExample(example: string) {
    setDescription(example);
    setError(null);
    setSubmittedJobId(null);
  }

  return (
    <main className="app-shell">
      <nav className="topbar" aria-label="Main navigation">
        <a className="brand" href="/" aria-label="FieldMind home">
          <span className="brand-mark"><Wrench size={17} strokeWidth={2.7} /></span>
          <span>fieldmind<span className="brand-dot">.</span></span>
        </a>
        <div className="nav-meta"><span className="status-dot" /> Available in your area <ArrowUpRight size={15} /></div>
      </nav>

      <section className="hero-grid">
        <div className="hero-copy">
          <p className="eyebrow"><Sparkles size={15} /> Home help, without the runaround</p>
          <h1>What needs<br /><em>fixing?</em></h1>
          <p className="intro">Describe the problem in your own words. We&apos;ll understand the issue, find the right local professional, and keep you posted.</p>

          <div className="confidence-row">
            <div className="confidence-icon"><ShieldCheck size={18} /></div>
            <div><strong>Trusted local pros</strong><span>Vetted, rated, and ready to help</span></div>
          </div>
        </div>

        <div className="request-panel">
          <div className="panel-heading"><div><span className="step-label">STEP 01 / REQUEST</span><h2>Tell us what&apos;s going on</h2></div><CircleHelp size={21} /></div>
          <form onSubmit={handleSubmit} noValidate>
            <label htmlFor="repair-description">Describe the problem</label>
            <div className={`textarea-wrap ${error ? "has-error" : ""}`}>
              <textarea id="repair-description" value={description} onChange={(event) => { setDescription(event.target.value); setError(null); setSubmittedJobId(null); }} placeholder="e.g. Water is leaking from the pipe under my kitchen sink..." maxLength={1000} aria-describedby="description-hint form-feedback" aria-invalid={Boolean(error)} />
              <span className="character-count">{description.length}/1000</span>
            </div>
            <div className="prompt-examples" aria-label="Example descriptions">
              {examplePrompts.map((example) => <button className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-[#e66d3f]" type="button" key={example} onClick={() => chooseExample(example)}>{example}</button>)}
            </div>
            <p id="description-hint" className="field-hint">Include what happened, where it is, and how urgent it feels.</p>
            {error && <p id="form-feedback" className="form-message error-message" role="alert">{error}</p>}
            {submittedJobId && <p id="form-feedback" className="form-message success-message" role="status"><Check size={16} /> Request received. Job {submittedJobId.slice(0, 8)} is being matched.</p>}
            <button className="submit-button focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#e66d3f]" type="submit" disabled={isSubmitting}>
              {isSubmitting ? <><span className="spinner" /> Finding your pro...</> : <>Find my professional <ArrowUpRight size={18} /></>}
            </button>
          </form>
          <div className="panel-footer"><span><Clock3 size={15} /> Usually matched in under 3 minutes</span><span><MapPin size={15} /> Local professionals</span></div>
        </div>
      </section>

      <footer className="bottom-note"><span>FIELD SERVICE, MADE HUMAN</span><span className="footer-line" /><span>Your home is in good hands.</span></footer>
    </main>
  );
}