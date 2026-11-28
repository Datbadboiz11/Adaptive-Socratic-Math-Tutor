/** Decorative foliage lives in the sidebar's free space, outside the controls. */
export function SidebarBotanical() {
  return <div className="sidebar-botanical" aria-hidden="true">
    <svg viewBox="0 0 208 190" fill="none" focusable="false">
      <g className="botanical-leaves">
        <path d="M112 62C87 60 69 44 74 24C96 25 111 40 112 62Z" />
        <path d="M121 90C122 66 140 48 160 50C159 72 143 87 121 90Z" />
        <path d="M135 119C111 123 89 111 83 92C105 87 126 99 135 119Z" />
        <path d="M152 145C149 121 165 100 184 96C191 119 176 139 152 145Z" />
        <path d="M178 174C153 181 131 171 120 152C141 145 163 152 178 174Z" />
      </g>
      <g className="botanical-leaves-light">
        <path d="M92 104C75 108 58 101 53 87C70 82 85 91 92 104Z" />
        <path d="M76 82C76 65 63 53 48 53C48 69 59 80 76 82Z" />
      </g>
      <g className="botanical-stems" strokeWidth="1.15" strokeLinecap="round">
        <path d="M196 188C155 160 126 117 107 44" />
        <path d="M111 62L87 36M121 90L148 61M135 119L97 101M152 145L177 110M178 174L135 158" />
        <path d="M139 189C111 165 89 125 72 70M92 104L64 93" />
      </g>
    </svg>
  </div>;
}
