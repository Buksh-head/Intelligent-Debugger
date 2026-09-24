import { useEffect, useMemo, useState } from 'react'
import { getCohortAnalytics } from './api'
import type { AnalyticsConcept, AnalyticsDateRange, AnalyticsResponse } from './types'
import pythonLogo from './assets/python.jpg'
import { ArrowLeft, ArrowRight, ChevronDown, LogOut, Sun, Moon, User } from 'lucide-react'

type InstructorDashboardProps = {
  onBack: () => void
}

const courseCodes = ['CSSE1001', 'CSSE2002', 'ENGG1001', 'DECO1800']
const themeOptions = [
  { label: 'Light', value: 'light' },
  { label: 'Dark', value: 'dark' },
  { label: 'Synthwave', value: 'synthwave' },
  { label: 'Luxury', value: 'luxury' },
  { label: 'Forest', value: 'forest' },
] as const

type Theme = (typeof themeOptions)[number]['value']
const themeStorageKey = 'debugging-assistant.theme'

const getInitialTheme = (): Theme => {
  const savedTheme = localStorage.getItem(themeStorageKey)
  const savedOption = themeOptions.find((option) => option.value === savedTheme)
  if (savedOption) return savedOption.value

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export default function InstructorDashboard({ onBack }: InstructorDashboardProps) {
  const [theme, setTheme] = useState<Theme>(getInitialTheme)
  const [selectedConcept, setSelectedConcept] = useState<string | null>(() => (
    new URLSearchParams(window.location.search).get('concept')
  ))
  const [dateRange, setDateRange] = useState<AnalyticsDateRange>('last_7_days')
  const [course, setCourse] = useState('')
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null)
  const [analyticsError, setAnalyticsError] = useState<string | null>(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem(themeStorageKey, theme)
  }, [theme])

  useEffect(() => {
    const handlePopState = () => {
      setSelectedConcept(new URLSearchParams(window.location.search).get('concept'))
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    getCohortAnalytics(dateRange, course || undefined)
      .then(setAnalytics)
      .catch((error: unknown) => setAnalyticsError(error instanceof Error ? error.message : 'Unable to load cohort analytics.'))
  }, [course, dateRange])

  const activeConcept = useMemo(
    () => (selectedConcept && analytics ? analytics.details[selectedConcept] : null),
    [analytics, selectedConcept],
  )

  const concepts: AnalyticsConcept[] = analytics?.concepts ?? []
  const overviewStats = analytics
    ? [
        { label: 'Analysed sessions', value: String(analytics.analysed_sessions) },
        { label: 'Detected errors', value: String(analytics.detected_errors) },
        { label: 'Most common concept', value: analytics.concepts[0]?.name ?? 'None recorded' },
      ]
    : []

  const chartPoints = activeConcept?.chart_points ?? []
  const chartMax = Math.max(...chartPoints.map((point) => point.count), 1)
  const chartWidth = 455
  const chartHeight = 170
  const chartLeft = 48
  const chartTop = 12
  const chartBottom = chartTop + chartHeight
  const chartStep = chartPoints.length > 1 ? chartWidth / (chartPoints.length - 1) : chartWidth
  const chartPath = chartPoints
    .map((point, index) => {
      const x = chartLeft + index * chartStep
      const y = chartBottom - (point.count / chartMax) * chartHeight
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
  const yTicks = Array.from({ length: 5 }, (_, index) => Math.round((chartMax * index) / 4))

  return (
    <div className="min-h-screen w-full bg-base-100 p-5 text-base-content">
      <header className="navbar mb-2">
        <div className="flex-1 flex items-center gap-3">
          <img src={pythonLogo} alt="Python Logo" className="h-[50px]" />
          <div>
            <h1 className="font-mono text-3xl font-semibold tracking-wider text-primary">INTELLIGENT PYTHON DEBUGGER</h1>
            <p className="mt-1">Instructor View</p>
          </div>
        </div>
        <div className="dropdown dropdown-end">
        <button
          type="button"
          tabIndex={0}
          className="btn btn-circle btn-primary h-15 w-15"
          aria-label="Open profile menu"
        >
          <User size={30} />
        </button>

        <div
          tabIndex={0}
          className="dropdown-content z-20 mt-3 w-64 rounded-xl border border-base-300 bg-base-100 p-4 shadow-xl"
        >

          {/* Profile */}
          <div className="mb-4 flex items-center gap-3 border-b border-base-300 pb-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-content">
              <User size={24} />
            </div>

            <div>
              <div className="font-semibold">
                Instructor
              </div>
              <div className="text-sm text-base-content/60">
                Dashboard account
              </div>
            </div>
          </div>


          {/* Theme toggle */}
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="font-medium">
                Theme
              </div>
              <div className="text-sm text-base-content/60">
                {theme === 'dark' ? 'Dark mode' : 'Light mode'}
              </div>
            </div>

            <button
              type="button"
              className="btn btn-sm btn-circle btn-outline"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>


          {/* Logout */}
          <button
            type="button"
            className="btn btn-outline btn-error w-full"
            onClick={onBack}
          >
            <LogOut size={16} />
            Log out
          </button>

        </div>
      </div>
      </header>

      <div className="flex min-h-0">
        <main className="flex-1 bg-base-100 px-[18px] py-[18px] min-[981px]:px-8 min-[981px]:pb-4 min-[981px]:pt-6">
          {analyticsError ? (
            <p className="rounded-xl border border-error/30 bg-error/10 p-5 text-error-content">{analyticsError}</p>
          ) : !analytics ? (
            <p className="rounded-xl border border-base-300 bg-base-200 p-5 text-base-content/70">Loading cohort analytics...</p>
          ) : activeConcept ? (
            <>
              <div className="mb-[22px] grid gap-4 min-[981px]:grid-cols-[1fr_auto_1fr] min-[981px]:items-start min-[981px]:gap-5">
                <div className="text-left min-[981px]:col-start-2 min-[981px]:row-start-1 min-[981px]:text-center">
                  <h1 className="text-[clamp(2rem,2.4vw,3rem)] font-bold leading-tight tracking-tight">{activeConcept.title}</h1>
                  <p className="mt-2 text-base text-base-content/65">{activeConcept.description}</p>
                </div>

                <div className="flex flex-wrap items-end gap-3.5 min-[981px]:col-start-1 min-[981px]:row-start-1 min-[981px]:pt-[22px]">
                  <button type="button" className="btn btn-outline" onClick={() => {
                    window.history.replaceState(null, '', window.location.pathname)
                    setSelectedConcept(null)
                  }}>
                    <ArrowLeft size={16} aria-hidden="true" />
                    Back to overview
                  </button>
                </div>

                <div className="flex min-w-[140px] flex-col gap-1.5 min-[981px]:col-start-3 min-[981px]:row-start-1 min-[981px]:justify-self-end">
                    <label className="text-xs text-base-content/70">Date range</label>
                    <select className="select select-bordered select-sm w-full bg-base-100 text-base-content" value={dateRange} onChange={(event) => setDateRange(event.target.value as AnalyticsDateRange)}>
                      <option value="today">Today</option>
                      <option value="last_7_days">Last 7 days</option>
                      <option value="last_month">Last month</option>
                      <option value="semester_2_2026">2026 Sem2</option>
                    </select>
                </div>
              </div>

              <div className="grid gap-[18px] min-[981px]:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                <div className="min-h-[400px] rounded-xl border border-base-300 bg-base-200 p-5 pb-[18px]">
                  <div className="mb-1.5 text-[1.05rem] font-semibold">Error frequency over time</div>
                  {chartPoints.length === 0 ? (
                    <p className="mt-4 text-sm text-base-content/60">No records found</p>
                  ) : <svg viewBox="0 0 520 230" className="mt-3 block h-[320px] w-full" role="img" aria-label="Error frequency over time">
                    {yTicks.map((tick, index) => {
                      const y = chartBottom - (index / 4) * chartHeight
                      return (
                        <g key={tick}>
                          <line x1={chartLeft} x2={chartLeft + chartWidth} y1={y} y2={y} stroke="rgba(75,85,99,0.22)" />
                          <text x={chartLeft - 8} y={y + 4} textAnchor="end" fill="#4b5563" className="text-[10px]">{tick}</text>
                        </g>
                      )
                    })}
                    <line x1={chartLeft} x2={chartLeft} y1={chartTop} y2={chartBottom} stroke="rgba(75,85,99,0.55)" />
                    <line x1={chartLeft} x2={chartLeft + chartWidth} y1={chartBottom} y2={chartBottom} stroke="rgba(75,85,99,0.55)" />
                    {chartPath && <path d={chartPath} fill="none" stroke="#51247a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />}
                    {chartPoints.map((point, index) => {
                      const x = chartLeft + index * chartStep
                      const y = chartBottom - (point.count / chartMax) * chartHeight
                      return (
                        <g key={`${point.label}-${index}`}>
                          <circle cx={x} cy={y} r="3.5" fill="#51247a" />
                          <text x={x} y={chartBottom + 18} textAnchor="middle" fill="#4b5563" className="text-[10px]">{point.label}</text>
                        </g>
                      )
                    })}
                  </svg>}
                </div>

                <div className="min-h-[260px] rounded-xl border border-base-300 bg-base-200 p-5 pb-[18px]">
                  <div className="mb-1.5 text-[1.05rem] font-semibold">Errors grouped under this type</div>
                  <ul className="mt-3.5 max-h-[260px] overflow-y-auto pr-2 list-none p-0">
                    {activeConcept.grouped_errors.length === 0 ? <li className="py-2.5 text-sm text-base-content/60">No records found</li> : activeConcept.grouped_errors.map((item) => (
                      <li key={item.label} className="flex items-center justify-between gap-4 border-b border-base-300 py-2.5 text-base-content/80 last:border-b-0">
                        <span>{item.label}</span>
                        <strong>{item.count}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="mt-[18px] rounded-xl border border-base-300 bg-base-200 p-5 pb-[18px]">
                <div className="mb-1.5 text-[1.05rem] font-semibold">Debugging assistance outcomes</div>
                <div className="mt-[18px] flex h-7 overflow-hidden rounded-lg border border-base-300 bg-base-100">
                  {activeConcept.outcomes.map((item) => (
                    <div key={item.label} className="h-full" style={{ width: `${item.percent}%` }}>
                      <div className={`h-full ${item.tone === 'resolved' ? 'bg-green-700' : item.tone === 'attempted' ? 'bg-amber-600' : 'bg-red-700'}`} />
                    </div>
                  ))}
                </div>

                <div className="mt-[18px] grid gap-5 min-[981px]:grid-cols-3">
                  {activeConcept.outcomes.length === 0 ? <p className="text-sm text-base-content/60">No records found</p> : activeConcept.outcomes.map((item) => (
                    <div key={item.label} className="text-base-content/80">
                      <div className="mb-2 text-xs">
                        <strong className={`text-2xl font-semibold tracking-tight ${item.tone === 'resolved' ? 'text-green-500' : item.tone === 'attempted' ? 'text-amber-400' : 'text-red-500'}`}>{item.count}</strong> • {item.percent}%
                      </div>
                      <span>{item.label}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-5">
                <div className="rounded-xl border border-base-300 bg-base-200 p-5 pb-[18px]">
                  <div className="mb-1.5 text-[1.05rem] font-semibold">Related teaching topics</div>
                  <p className="m-0 text-xs text-base-content/60">Suggested from the error taxonomy—not an automated teaching decision.</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {activeConcept.topics.length === 0 ? <p className="text-sm text-base-content/60">No records found</p> : activeConcept.topics.map((topic) => (
                      <span key={topic} className="badge badge-outline h-auto px-2.5 py-1.5 text-[0.85rem] text-base-content/80">
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="mb-[22px] grid gap-4 min-[981px]:flex min-[981px]:items-start min-[981px]:justify-between min-[981px]:gap-5">
                <div className="flex-1">
                <h1 className="text-[clamp(2rem,2.4vw,3rem)] font-bold leading-tight tracking-tight">
                  {course ? `${course} cohort error overview` : 'All Cohort error overview'}
                </h1>
                </div>

                <div className="flex flex-wrap items-end gap-3.5">
                  <div className="flex min-w-[140px] flex-col gap-1.5">
                    <label className="text-xs text-base-content/70">Class</label>
                    <select className="select select-bordered select-sm w-full bg-base-100 text-base-content" value={course} onChange={(event) => setCourse(event.target.value)}>
                      <option value="">All classes</option>
                      {courseCodes.map((courseCode) => <option key={courseCode} value={courseCode}>{courseCode}</option>)}
                    </select>
                  </div>

                  <div className="flex min-w-[140px] flex-col gap-1.5">
                    <label className="text-xs text-base-content/70">Date range</label>
                    <select className="select select-bordered select-sm w-full bg-base-100 text-base-content" value={dateRange} onChange={(event) => setDateRange(event.target.value as AnalyticsDateRange)}>
                      <option value="today">Today</option>
                      <option value="last_7_days">Last 7 days</option>
                      <option value="last_month">Last month</option>
                      <option value="semester_2_2026">2026 Sem 2</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="mb-5 grid gap-[18px] min-[981px]:grid-cols-3">
                {overviewStats.map((stat) => (
                  <div key={stat.label} className="flex min-h-[110px] flex-col justify-center rounded-xl border border-base-300 bg-base-200 px-5 py-[18px]">
                    <div className="mb-2 text-sm text-base-content/70">{stat.label}</div>
                    <div className="text-[clamp(1.6rem,2vw,2.5rem)] font-semibold leading-tight tracking-tight">{stat.value}</div>
                  </div>
                ))}
              </div>

              <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
              <div className="flex h-[calc(100vh-420px)] min-h-[400px] flex-col rounded-xl border border-base-300 bg-base-200 p-5 pb-[18px]">
                <div>
                  <div>
                    <div className="mb-1.5 text-[1.05rem] font-semibold">Most common error types</div>
                  </div>
                </div>

                <div className="mt-4 h-full overflow-y-auto space-y-1.5 pr-2">
                  {concepts.length === 0 ? <p className="py-2.5 text-sm text-base-content/60">No records found</p> : concepts.map((concept) => (
                    <button
                      key={concept.name}
                      type="button"
                      className="grid w-full cursor-pointer grid-cols-[minmax(110px,180px)_minmax(0,1fr)_78px_112px] items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2.5 text-left text-inherit transition hover:border-primary/50 hover:bg-base-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                      aria-label={`View details for ${concept.name}`}
                      onClick={() => {
                        const params = new URLSearchParams(window.location.search)
                        params.set('concept', concept.name)
                        window.history.pushState(null, '', `${window.location.pathname}?${params.toString()}`)
                        setSelectedConcept(concept.name)
                      }}
                    >
                      <span className="font-medium text-base-content/90">{concept.name}</span>
                      <span className="h-3 w-full overflow-hidden rounded-full border border-base-300 bg-base-200">
                        <span className="block h-full rounded-full bg-primary/80" style={{ width: `${concept.percent}%` }} />
                      </span>
                      <span className="w-full whitespace-nowrap text-right text-xs text-base-content/70">{concept.count} • {concept.percent}%</span>
                      <span className="flex w-full items-center justify-end gap-1 whitespace-nowrap text-right text-base font-medium text-primary">See details <ArrowRight size={16} aria-hidden="true" /></span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
              <div className="flex h-[calc(100vh-420px)] min-h-[400px] flex-col rounded-xl border border-base-300 bg-base-200 p-5 pb-[18px]">
                <div className="mb-1.5 text-[1.05rem] font-semibold">
                  Recurring raw errors
                </div>

                <ul className="mt-3.5 min-h-0 flex-1 overflow-y-auto pr-2 list-none p-0">
                    {analytics.recurring_errors.length === 0 ? <li className="py-2.5 text-sm text-base-content/60">No records found</li> : analytics.recurring_errors.map((item) => (
                      <li key={item.label} className="flex items-center justify-between gap-4 border-b border-base-300 py-2.5 text-base-content/80 last:border-b-0">
                        <span>{item.label}</span>
                        <strong>{item.count}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  )
}
