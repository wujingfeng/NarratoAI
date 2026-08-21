import { createContext, useContext, useEffect, useState, type PropsWithChildren } from 'react'
import { adminApi } from '../api/admin'
import { clearToken, getToken, setToken } from '../api/client'
import type { AdminProfile } from '../types/api'

interface AuthState { profile?: AdminProfile; ready: boolean; signIn: (username: string, password: string) => Promise<void>; signOut: () => Promise<void> }
const AuthContext = createContext<AuthState | null>(null)
export function AuthProvider({ children }: PropsWithChildren) {
  const [profile, setProfile] = useState<AdminProfile>(); const [ready, setReady] = useState(false)
  useEffect(() => { if (!getToken()) { setReady(true); return }; adminApi.me().then(setProfile).catch(clearToken).finally(() => setReady(true)) }, [])
  const signIn = async (username: string, password: string) => { const data = await adminApi.login(username, password); setToken(data.token); setProfile(data.admin) }
  const signOut = async () => { try { await adminApi.logout() } finally { clearToken(); setProfile(undefined) } }
  return <AuthContext.Provider value={{ profile, ready, signIn, signOut }}>{children}</AuthContext.Provider>
}
export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error('AuthProvider is required'); return value }
