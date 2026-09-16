interface Config {
    apiUrl: string;
    timeoutMs: number;
}

export const defaultConfig: Config = {
    apiUrl: "http://localhost:8080",
    timeoutMs: 5000
};
