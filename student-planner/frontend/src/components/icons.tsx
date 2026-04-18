import type { ReactNode, SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & {
  title?: string
}

function BaseIcon({ title, children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
      {...props}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  )
}

export function ChatIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 6.2A2.2 2.2 0 0 1 6.2 4h11.6A2.2 2.2 0 0 1 20 6.2v7.6a2.2 2.2 0 0 1-2.2 2.2H11l-4.2 3v-3H6.2A2.2 2.2 0 0 1 4 13.8Z" />
    </BaseIcon>
  )
}

export function CalendarIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect x="3.5" y="5.5" width="17" height="15" rx="3" />
      <path d="M7.5 3.5v4M16.5 3.5v4M3.5 10.5h17" />
    </BaseIcon>
  )
}

export function UserIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5.5 19a6.5 6.5 0 0 1 13 0" />
    </BaseIcon>
  )
}

export function PlusIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M12 5v14M5 12h14" />
    </BaseIcon>
  )
}

export function PaperclipIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="m10.7 13.3 5.2-5.2a2.8 2.8 0 0 0-4-4l-6 6a4.2 4.2 0 1 0 6 6l6.3-6.3" />
    </BaseIcon>
  )
}

export function MicIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect x="9" y="3.5" width="6" height="11" rx="3" />
      <path d="M6.5 11.5a5.5 5.5 0 0 0 11 0M12 17v3.5M9 20.5h6" />
    </BaseIcon>
  )
}

export function SendIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="m4 12 15-7-3.2 14L11.4 13z" />
      <path d="M11.4 13 19 5" />
    </BaseIcon>
  )
}

export function CourseIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M3.5 8.5 12 4l8.5 4.5L12 13z" />
      <path d="M6 10v5.5c0 .9 2.7 2 6 2s6-1.1 6-2V10" />
    </BaseIcon>
  )
}

export function TaskIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect x="4.5" y="4.5" width="15" height="15" rx="3" />
      <path d="m8.3 12 2.2 2.2 5.2-5.2" />
    </BaseIcon>
  )
}

export function ChevronLeftIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="m14.5 6.5-5 5.5 5 5.5" />
    </BaseIcon>
  )
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="m9.5 6.5 5 5.5-5 5.5" />
    </BaseIcon>
  )
}

export function BookIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4.5 6.5a2 2 0 0 1 2-2H19.5v15H7a2.5 2.5 0 0 1-2.5-2.5z" />
      <path d="M7 8h8M7 11h8M7 14h6" />
    </BaseIcon>
  )
}

export function SlidersIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 6h16M4 12h16M4 18h16" />
      <circle cx="9" cy="6" r="2" />
      <circle cx="15" cy="12" r="2" />
      <circle cx="11" cy="18" r="2" />
    </BaseIcon>
  )
}

export function BellIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M8 17h8c-.7-.8-1.1-1.8-1.1-2.9v-2a3.9 3.9 0 0 0-7.8 0v2c0 1.1-.4 2.1-1.1 2.9Z" />
      <path d="M10.2 19a1.8 1.8 0 0 0 3.6 0" />
    </BaseIcon>
  )
}

export function ExitIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M10 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2H10" />
      <path d="M14 8.5 19 12l-5 3.5M19 12H9" />
    </BaseIcon>
  )
}
