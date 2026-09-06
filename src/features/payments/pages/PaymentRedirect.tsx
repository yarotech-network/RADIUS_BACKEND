import { Navigate, useParams } from 'react-router';

/** `/payments/:id` is a shareable deep link; the list page opens the drawer from `?payment=`. */
export function PaymentRedirect() {
  const { id } = useParams();
  return <Navigate to={id ? `/payments?payment=${encodeURIComponent(id)}` : '/payments'} replace />;
}
