export type AuthMe = {
  user: {
    id: number
    name: string
    email: string | null
    phone: string | null
    is_active: boolean
  }
  is_super_admin: boolean
  /** Rôle global `admin` — équipe ControlPlay (hors client salle_admin). */
  is_platform_staff: boolean
  /** Permissions déléguées par le super_admin : operations | users */
  staff_permissions: string[]
  is_global_salle_admin: boolean
  is_gerant_only: boolean
}

export type NavItem = { label: string; to: string }

export type AdminBootstrap = {
  nav: NavItem[]
  is_super_admin: boolean
  is_gerant_only: boolean
  can_manage_providers?: boolean
  staff_permissions?: string[]
}
