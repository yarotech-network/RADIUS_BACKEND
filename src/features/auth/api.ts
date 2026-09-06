import { http } from '@/services/api/http';
import type {
  AcceptInvitationRequest,
  ChangePasswordRequest,
  PasswordResetConfirmRequest,
  PasswordResetRequest,
  SimpleMessage,
  StaffAssignment,
  UpdateUserRequest,
  User,
} from '@/types/api';

export { authApi } from '@/services/auth/session';

export const accountApi = {
  updateProfile(payload: UpdateUserRequest) {
    return http.patch<User>('/auth/user/', payload, { tenantId: null });
  },
  changePassword(payload: ChangePasswordRequest) {
    return http.post<SimpleMessage>('/auth/change-password/', payload, { tenantId: null });
  },
  requestPasswordReset(payload: PasswordResetRequest) {
    return http.post<SimpleMessage>('/auth/password-reset/', payload, {
      anonymous: true,
      tenantId: null,
    });
  },
  confirmPasswordReset(payload: PasswordResetConfirmRequest) {
    return http.post<SimpleMessage>('/auth/password-reset/confirm/', payload, {
      anonymous: true,
      tenantId: null,
    });
  },
  /** Works both anonymously (creates an account) and signed-in (links to the current account). */
  acceptInvitation(payload: AcceptInvitationRequest, anonymous: boolean) {
    return http.post<StaffAssignment>('/staff-invitations/accept/', payload, {
      anonymous,
      tenantId: null,
    });
  },
};
