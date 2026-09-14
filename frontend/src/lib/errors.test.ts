import { describe, it, expect } from 'vitest';
import { getErrorMessage } from './errors';

describe('getErrorMessage', () => {
    it('extrae message de un Error estándar', () => {
        expect(getErrorMessage(new Error('fallo de red'))).toBe('fallo de red');
    });

    it('devuelve el string cuando el error es un string', () => {
        expect(getErrorMessage('algo salió mal')).toBe('algo salió mal');
    });

    it('extrae message de objetos con propiedad message', () => {
        expect(getErrorMessage({ message: 'error de api' })).toBe('error de api');
    });

    it('convierte message numérico a string', () => {
        expect(getErrorMessage({ message: 42 })).toBe('42');
    });

    it('devuelve mensaje por defecto para null/undefined/primitivas', () => {
        expect(getErrorMessage(null)).toBe('Error inesperado');
        expect(getErrorMessage(undefined)).toBe('Error inesperado');
        expect(getErrorMessage(123)).toBe('Error inesperado');
    });

    it('devuelve mensaje por defecto para objetos sin message', () => {
        expect(getErrorMessage({ code: 500 })).toBe('Error inesperado');
    });
});
