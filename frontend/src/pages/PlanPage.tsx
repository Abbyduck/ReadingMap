import { CalendarDays, Check, ChevronLeft, Clock3 } from "lucide-react";
import { ProductHeader } from "@/components/layout/ProductHeader";

const tasks = [
  { title: "亲子共读 Frog and Toad", detail: "20 分钟 · 睡前", done: true },
  { title: "听一集分级配套音频", detail: "10 分钟 · 通勤", done: false },
  { title: "把今天喜欢的书放进书架", detail: "完成后记录一句话", done: false }
];

export function PlanPage() {
  return (
    <main className="product-root min-h-screen bg-[#f7f8f3] text-[#18352e]">
      <ProductHeader current="plan" />
      <section className="mx-auto w-full max-w-5xl px-5 py-12 sm:px-8 lg:py-20">
        <a href="/" className="inline-flex items-center gap-2 text-sm font-bold text-[#58716a]"><ChevronLeft size={16} />回到阅读房间</a>
        <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_340px]">
          <div>
            <p className="text-[11px] font-black tracking-[.16em] text-[#ad7124]">SUNDAY · 14 SEPTEMBER</p>
            <h1 className="mt-4 font-serif text-5xl font-semibold tracking-[-.045em] sm:text-6xl">我的阅读计划</h1>
            <p className="mt-5 max-w-xl text-base leading-8 text-[#657972]">先把今天读什么安排清楚。这里暂时使用 mock 数据，之后再接真实计划。</p>
            <div className="mt-10 grid gap-3">
              {tasks.map((task) => (
                <article key={task.title} className="flex items-center gap-4 rounded-3xl border border-[#dce4de] bg-white/80 p-5 shadow-[0_14px_40px_rgba(31,64,55,.06)]">
                  <span className={`grid size-10 place-items-center rounded-2xl ${task.done ? "bg-[#286353] text-white" : "bg-[#edf2ee] text-[#6d8079]"}`}>{task.done ? <Check size={18} /> : <Clock3 size={18} />}</span>
                  <div><h2 className="font-serif text-xl font-semibold">{task.title}</h2><p className="mt-1 text-sm text-[#788881]">{task.detail}</p></div>
                </article>
              ))}
            </div>
          </div>
          <aside className="h-fit rounded-[32px] bg-[#f0c468] p-7 text-[#3d2c13] shadow-[0_24px_60px_rgba(111,72,20,.16)]">
            <CalendarDays size={30} />
            <p className="mt-10 text-sm font-bold">本周阅读</p><strong className="mt-2 block font-serif text-5xl">4 / 6</strong><p className="mt-4 text-sm leading-6 text-[#725429]">已经完成四次阅读，连续阅读 3 天。</p>
          </aside>
        </div>
      </section>
    </main>
  );
}
