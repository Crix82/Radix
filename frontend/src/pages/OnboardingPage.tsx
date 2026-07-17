import { useNavigate } from "react-router-dom";

import { t } from "../i18n";

const steps = [
  { title: t.pages.onboarding.step1Title, desc: t.pages.onboarding.step1Desc },
  { title: t.pages.onboarding.step2Title, desc: t.pages.onboarding.step2Desc },
  { title: t.pages.onboarding.step3Title, desc: t.pages.onboarding.step3Desc },
];

export function OnboardingPage() {
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-[660px] pt-[30px]">
      <div className="mb-[10px] font-mono text-[11px] tracking-[.12em] text-petrol">
        {t.pages.onboarding.eyebrow}
      </div>
      <h1 className="mb-2 text-[26px] font-semibold tracking-[-.015em]">
        {t.pages.onboarding.title}
      </h1>
      <p className="mb-7 max-w-[480px] text-[14px] text-ink2">{t.pages.onboarding.lead}</p>

      <div className="mb-7 flex flex-col">
        {steps.map((step, i) => (
          <div key={step.title} className="relative flex gap-4 pb-[22px] last:pb-0">
            {i < steps.length - 1 && (
              <span className="absolute bottom-[2px] left-[15px] top-[34px] w-[2px] bg-line" />
            )}
            <div className="flex h-8 w-8 flex-none items-center justify-center rounded-full border border-[#cfe0e3] bg-petrol-tint text-[14px] font-bold text-petrol">
              {i + 1}
            </div>
            <div>
              <div className="pt-[5px] text-[14px] font-semibold">{step.title}</div>
              <div className="mt-[2px] text-[12.5px] text-ink2">{step.desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="mb-[22px] flex items-center gap-[18px]">
        <button className="btn-primary" onClick={() => navigate("/sources")}>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            aria-hidden="true"
            className="h-[15px] w-[15px]"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          {t.pages.onboarding.cta}
        </button>
      </div>
      <div className="font-mono text-[11px] text-ink3">{t.pages.onboarding.note}</div>
    </div>
  );
}
